// FH6 Car Mod Manager integration. Upstream ForzaTech Studio retains its MIT license.
// Speed and disk helpers for the one-shot thumbnail renderer; unused by the editor.
using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text;

namespace ForzaTechStudio;

/// <summary>Builds the merged vehicle scene without recompressing anything.</summary>
internal static class ThumbnailArchive
{
    // Every entry type the thumbnail path reads from a vehicle archive: scene data parsed by
    // ViewportPage.LoadZip, and textures/materials indexed by SwatchbinArchiveService.
    private static readonly string[] RenderExtensions =
    {
        ".modelbin", ".bin", ".carbin", ".xml", ".avpins", ".gr2", ".gsf", ".clipd",
        ".swatchbin", ".pb", ".materialbin",
    };

    public static bool IsRenderEntry(string name) =>
        RenderExtensions.Any(extension => name.EndsWith(extension, StringComparison.OrdinalIgnoreCase));

    /// <summary>
    /// Writes a ZIP whose entries are byte-for-byte copies of the source entries' compressed
    /// data (same method, CRC and sizes).  Nothing is inflated or deflated, so the merge is a
    /// sequential copy and the scene is never larger than its parts.  Throws
    /// <see cref="InvalidDataException"/> when the result would need ZIP64.
    /// </summary>
    public static void WriteRaw(IReadOnlyList<(string Name, CustomZipFile Zip, CustomZipFile.ZipEntryInfo Entry)> files,
                                Stream output, Action? check = null)
    {
        if (files.Count > ushort.MaxValue)
            throw new InvalidDataException("Too many entries for a non-ZIP64 scene.");
        var writer = new BinaryWriter(output, Encoding.UTF8, leaveOpen: true);
        var offsets = new List<uint>(files.Count);
        var names = new List<byte[]>(files.Count);
        foreach (var (name, zip, entry) in files)
        {
            check?.Invoke();
            byte[] nameBytes = Encoding.UTF8.GetBytes(name);
            offsets.Add(Offset(output.Position));
            names.Add(nameBytes);
            writer.Write(0x04034b50u);
            WriteCommon(writer, name, entry, nameBytes.Length);
            writer.Write((ushort)0); // extra length
            writer.Write(nameBytes);
            writer.Flush();
            long start = output.Position;
            zip.CopyRawEntry(entry, output);
            if (output.Position - start != entry.CompressedSize)
                throw new InvalidDataException("Short entry copy: " + name);
            Offset(output.Position);
        }
        uint directory = Offset(output.Position);
        for (int i = 0; i < files.Count; i++)
        {
            var (name, _, entry) = files[i];
            writer.Write(0x02014b50u);
            writer.Write((ushort)20); // version made by
            WriteCommon(writer, name, entry, names[i].Length);
            writer.Write((ushort)0); // extra length
            writer.Write((ushort)0); // comment length
            writer.Write((ushort)0); // disk number
            writer.Write((ushort)0); // internal attributes
            writer.Write(0u);        // external attributes
            writer.Write(offsets[i]);
            writer.Write(names[i]);
        }
        writer.Flush();
        uint directorySize = Offset(output.Position) - directory;
        writer.Write(0x06054b50u);
        writer.Write((ushort)0);
        writer.Write((ushort)0);
        writer.Write((ushort)files.Count);
        writer.Write((ushort)files.Count);
        writer.Write(directorySize);
        writer.Write(directory);
        writer.Write((ushort)0);
        writer.Flush();
    }

    private static void WriteCommon(BinaryWriter writer, string name, CustomZipFile.ZipEntryInfo entry, int nameLength)
    {
        writer.Write((ushort)20);                                       // version needed
        writer.Write((ushort)(name.Any(c => c > 0x7f) ? 0x0800 : 0));   // UTF-8 names when needed
        writer.Write(entry.CompressionMethod);
        writer.Write((ushort)0);                                        // 00:00:00
        writer.Write((ushort)0x21);                                     // 1980-01-01
        writer.Write(entry.Crc);
        writer.Write(entry.CompressedSize);
        writer.Write(entry.UncompressedSize);
        writer.Write((ushort)nameLength);
    }

    private static uint Offset(long position) =>
        position <= uint.MaxValue ? (uint)position : throw new InvalidDataException("Scene would exceed 4 GiB without ZIP64.");
}

/// <summary>
/// Keeps each archive open with its directory indexed for the life of the renderer process.
/// Looking up one texture used to reopen the archive and re-parse its whole directory, once
/// per texture, for the vehicle scene and for the game's large shared texture archives.
/// </summary>
internal static class ZipIndexCache
{
    internal sealed class Index
    {
        public CustomZipFile Zip { get; init; } = null!;
        public Dictionary<string, CustomZipFile.ZipEntryInfo> Entries { get; init; } = null!;
        public long Length { get; init; }
        public DateTime Modified { get; init; }
    }

    private static readonly Dictionary<string, Index?> Cache = new(StringComparer.OrdinalIgnoreCase);
    private static readonly object Gate = new();

    public static string Normalize(string? value) => (value ?? string.Empty).Replace('\\', '/').TrimStart('/');

    /// <summary>Returns the archive's index, or null when it cannot be read by CustomZipFile.</summary>
    public static Index? Get(string zipPath)
    {
        string fullPath = Path.GetFullPath(zipPath);
        var info = new FileInfo(fullPath);
        if (!info.Exists) return null;
        lock (Gate)
        {
            if (Cache.TryGetValue(fullPath, out var cached)
                && (cached == null || (cached.Length == info.Length && cached.Modified == info.LastWriteTimeUtc)))
                return cached;
            cached?.Zip.Dispose();
            Index? index = null;
            try
            {
                var zip = new CustomZipFile(fullPath);
                try
                {
                    var entries = new Dictionary<string, CustomZipFile.ZipEntryInfo>(StringComparer.OrdinalIgnoreCase);
                    foreach (var entry in zip.GetEntries())
                        if (!entry.IsDirectory) entries.TryAdd(Normalize(entry.Name), entry);
                    index = new Index { Zip = zip, Entries = entries, Length = info.Length, Modified = info.LastWriteTimeUtc };
                }
                catch
                {
                    zip.Dispose();
                    throw;
                }
            }
            catch
            {
                index = null; // callers fall back to System.IO.Compression
            }
            Cache[fullPath] = index;
            return index;
        }
    }

    public static bool TryFind(string zipPath, string entryName, out Index? index, out CustomZipFile.ZipEntryInfo? entry)
    {
        entry = null;
        index = Get(zipPath);
        return index != null && index.Entries.TryGetValue(Normalize(entryName), out entry);
    }
}

/// <summary>
/// Drops the largest mip levels of a 2D DDS texture.  A 640x360 thumbnail never samples
/// 2K-4K levels, but decoding, uploading and holding them dominated renderer memory.
/// Anything the trimmer does not fully understand is returned unchanged.
/// </summary>
internal static class DdsMipTrimmer
{
    private const uint Magic = 0x20534444;          // 'DDS '
    private const uint FourCcFlag = 0x4;
    private const uint Dx10 = 0x30315844;           // 'DX10'
    private const uint MipCountFlag = 0x20000;
    private const uint LinearSizeFlag = 0x80000;
    private const uint PitchFlag = 0x8;
    private const uint CubeMap = 0x200, Volume = 0x200000;

    public static byte[] Trim(byte[] dds, int maxDimension)
    {
        try
        {
            return TrimCore(dds, maxDimension) ?? dds;
        }
        catch
        {
            return dds;
        }
    }

    private static uint U32(byte[] data, int offset) => BitConverter.ToUInt32(data, offset);

    private static byte[]? TrimCore(byte[] dds, int maxDimension)
    {
        if (dds.Length < 128 || U32(dds, 0) != Magic || U32(dds, 4) != 124) return null;
        uint flags = U32(dds, 8), height = U32(dds, 12), width = U32(dds, 16);
        uint mips = (flags & MipCountFlag) != 0 ? U32(dds, 28) : 1;
        uint pixelFlags = U32(dds, 80), fourCc = U32(dds, 84), bitCount = U32(dds, 88);
        uint caps2 = U32(dds, 112);
        if (mips <= 1 || width == 0 || height == 0 || Math.Max(width, height) <= maxDimension) return null;
        if ((caps2 & (CubeMap | Volume)) != 0) return null;

        int dataStart = 128;
        int blockBytes, pixelBytes = 0;
        if ((pixelFlags & FourCcFlag) != 0 && fourCc == Dx10)
        {
            if (dds.Length < 148) return null;
            uint format = U32(dds, 128), dimension = U32(dds, 132), misc = U32(dds, 136), arraySize = U32(dds, 140);
            if (dimension != 3 || arraySize != 1 || (misc & 0x4) != 0) return null; // 2D, single, not a cube
            dataStart = 148;
            blockBytes = DxgiBlockBytes(format);
            if (blockBytes == 0)
            {
                pixelBytes = DxgiPixelBytes(format);
                if (pixelBytes == 0) return null;
            }
        }
        else if ((pixelFlags & FourCcFlag) != 0)
        {
            blockBytes = FourCcBlockBytes(fourCc);
            if (blockBytes == 0) return null;
        }
        else
        {
            blockBytes = 0;
            pixelBytes = bitCount == 32 ? 4 : 0;
            if (pixelBytes == 0) return null;
        }

        long LevelSize(uint w, uint h) => blockBytes > 0
            ? Math.Max(1, (w + 3) / 4) * (long)Math.Max(1, (h + 3) / 4) * blockBytes
            : (long)Math.Max(1, w) * Math.Max(1, h) * pixelBytes;

        long total = 0;
        uint lw = width, lh = height;
        for (uint i = 0; i < mips; i++)
        {
            total += LevelSize(lw, lh);
            lw = Math.Max(1, lw / 2);
            lh = Math.Max(1, lh / 2);
        }
        if (dataStart + total > dds.Length) return null; // not a plain mip chain: leave it alone

        long skipBytes = 0;
        uint skip = 0, w = width, h = height;
        while (skip < mips - 1 && Math.Max(w, h) > maxDimension)
        {
            skipBytes += LevelSize(w, h);
            w = Math.Max(1, w / 2);
            h = Math.Max(1, h / 2);
            skip++;
        }
        if (skip == 0) return null;

        long keep = total - skipBytes;
        var result = new byte[dataStart + keep];
        Buffer.BlockCopy(dds, 0, result, 0, dataStart);
        Buffer.BlockCopy(dds, (int)(dataStart + skipBytes), result, dataStart, (int)keep);
        BitConverter.TryWriteBytes(new Span<byte>(result, 12, 4), h);
        BitConverter.TryWriteBytes(new Span<byte>(result, 16, 4), w);
        BitConverter.TryWriteBytes(new Span<byte>(result, 28, 4), mips - skip);
        uint pitch = blockBytes > 0 ? (uint)LevelSize(w, h) : w * (uint)pixelBytes;
        if ((flags & (LinearSizeFlag | PitchFlag)) != 0)
            BitConverter.TryWriteBytes(new Span<byte>(result, 20, 4), pitch);
        return result;
    }

    private static int FourCcBlockBytes(uint fourCc) => Encoding.ASCII.GetString(BitConverter.GetBytes(fourCc)) switch
    {
        "DXT1" or "ATI1" or "BC4U" or "BC4S" => 8,
        "DXT2" or "DXT3" or "DXT4" or "DXT5" or "ATI2" or "BC5U" or "BC5S" => 16,
        _ => 0,
    };

    private static int DxgiBlockBytes(uint format) => format switch
    {
        >= 70 and <= 72 => 8,   // BC1
        >= 73 and <= 78 => 16,  // BC2, BC3
        >= 79 and <= 81 => 8,   // BC4
        >= 82 and <= 84 => 16,  // BC5
        >= 94 and <= 99 => 16,  // BC6H, BC7
        _ => 0,
    };

    private static int DxgiPixelBytes(uint format) => format switch
    {
        >= 27 and <= 32 => 4,   // R8G8B8A8
        >= 87 and <= 93 => 4,   // B8G8R8A8 / B8G8R8X8
        _ => 0,
    };
}

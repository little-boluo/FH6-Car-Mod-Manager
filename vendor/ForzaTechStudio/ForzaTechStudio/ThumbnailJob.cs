// FH6 Car Mod Manager integration. Upstream ForzaTech Studio retains its MIT license.
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.IO.Compression;
using System.Linq;
using System.Text;
using System.Text.Json;
using System.Threading.Tasks;

namespace ForzaTechStudio;

internal sealed class ThumbnailJob
{
    public string Input { get; set; } = "";
    public string? BaseArchive { get; set; }
    public string? GameRoot { get; set; }
    public string Output { get; set; } = "";
    public int Width { get; set; } = 640;
    public int Height { get; set; } = 360;
    public static bool Probe => Environment.GetCommandLineArgs().Contains("--fh6-renderer-check");
    public static bool Enabled => Probe || Environment.GetCommandLineArgs().Contains("--fh6-thumbnail-request");
    public static ThumbnailJob? Current { get; private set; }

    public static ThumbnailJob Read()
    {
        var args = Environment.GetCommandLineArgs();
        int i = Array.IndexOf(args, "--fh6-thumbnail-request");
        if (i < 0 || i + 1 >= args.Length) throw new ArgumentException("Missing thumbnail request JSON.");
        var job = JsonSerializer.Deserialize<ThumbnailJob>(File.ReadAllText(args[i+1]))
            ?? throw new InvalidDataException("Invalid request JSON.");
        if (!Path.IsPathFullyQualified(job.Input) || !File.Exists(job.Input)
            || !Path.IsPathFullyQualified(job.Output) || !job.Output.EndsWith(".png", StringComparison.OrdinalIgnoreCase))
            throw new ArgumentException("Input must exist; output must be an absolute PNG path.");
        if (job.Width is < 64 or > 2048 || job.Height is < 64 or > 2048)
            throw new ArgumentException("Invalid image dimensions.");
        Encoding.RegisterProvider(CodePagesEncodingProvider.Instance);
        Current = job;
        return job;
    }

    public static void CheckGame()
    {
        var processes = Process.GetProcessesByName("forzahorizon6");
        bool running = processes.Length > 0;
        foreach (var p in processes) p.Dispose();
        if (running) throw new InvalidOperationException("FH6 is running; thumbnail generation paused.");
    }

    public static void Fail(Exception error)
    {
        RendererDiagnostics.Write("Fatal: " + error);
        try
        {
            if (Current != null)
                File.WriteAllText(Path.ChangeExtension(Current.Output, ".error.txt"), error.ToString());
        }
        finally { Environment.Exit(2); }
    }

    // Overlay the mod on a COPY of the matching original car. Never touch either source.
    // CustomZipFile supports Forza compression methods that System.IO.Compression cannot read.
    public async Task<string> PrepareArchiveAsync()
    {
        CheckGame();
        if (string.IsNullOrWhiteSpace(BaseArchive) || !File.Exists(BaseArchive)) return Input;
        string merged = Path.Combine(Path.GetDirectoryName(Output)!, "scene.zip");
        // Enumerating processes per entry made the merge itself slow; a few checks a second suffice
        // (the manager also stops the renderer as soon as the game starts).
        var clock = Stopwatch.StartNew();
        long lastCheck = long.MinValue / 2;
        void CheckGameThrottled()
        {
            if (clock.ElapsedMilliseconds - lastCheck < 250) return;
            lastCheck = clock.ElapsedMilliseconds;
            CheckGame();
        }
        await Task.Run(() =>
        {
            using var basis = new CustomZipFile(BaseArchive);
            using var mod = new CustomZipFile(Input);
            var files = new Dictionary<string, (CustomZipFile Zip, CustomZipFile.ZipEntryInfo Entry)>(StringComparer.OrdinalIgnoreCase);
            foreach (var zip in new[] { basis, mod })
            {
                var seen = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
                foreach (var entry in zip.GetEntries().Where(e => !e.IsDirectory))
                {
                    string name = entry.Name.Replace('\\', '/').TrimStart('/');
                    if (name.Split('/').Any(p => p == "..") || name.Contains(':'))
                        throw new InvalidDataException("Unsafe ZIP entry path.");
                    if (!seen.Add(name)) throw new InvalidDataException("Ambiguous duplicate ZIP entry: " + name);
                    // Only what the thumbnail actually reads goes into the scene (audio and other
                    // data never did anything here but cost time and temporary disk space).
                    if (!ThumbnailArchive.IsRenderEntry(name)) continue;
                    if (entry.CompressionMethod is not (0 or 8 or 21))
                        throw new InvalidDataException("Unsupported ZIP compression: " + entry.CompressionMethod);
                    if (entry.UncompressedSize > 512L*1024*1024)
                        throw new InvalidDataException("Vehicle archive entry exceeds thumbnail limits.");
                    files[name] = (zip, entry);
                }
            }
            if (files.Count > 60000 || files.Values.Sum(v => (long)v.Entry.UncompressedSize) > 4L*1024*1024*1024)
                throw new InvalidDataException("Vehicle archive exceeds thumbnail limits.");
            var ordered = files.Select(pair => (pair.Key, pair.Value.Zip, pair.Value.Entry)).ToList();
            try
            {
                // Copy each entry's compressed bytes as they are: no inflate/deflate work, and the
                // scene is never larger than the entries it needs.
                using var output = new FileStream(merged, FileMode.Create, FileAccess.Write, FileShare.None, 1 << 20);
                ThumbnailArchive.WriteRaw(ordered, output, CheckGameThrottled);
                RendererDiagnostics.Write($"Scene: {ordered.Count} entries copied without recompression");
            }
            catch (InvalidDataException error) when (error.Message.Contains("ZIP64"))
            {
                RendererDiagnostics.Write("Scene needs ZIP64; recompressing instead: " + error.Message);
                using var target = new ZipArchive(File.Create(merged), ZipArchiveMode.Create);
                foreach (var (name, zip, entry) in ordered)
                {
                    CheckGameThrottled();
                    using var stream = target.CreateEntry(name, CompressionLevel.Fastest).Open();
                    zip.ExtractToStream(entry, stream);
                }
            }
        });
        return merged;
    }
}

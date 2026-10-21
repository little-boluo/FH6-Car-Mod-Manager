using System;
using System.IO;
using System.Threading;

namespace ForzaTechStudio;

internal static class RendererDiagnostics
{
    private static readonly object Gate = new();
    private static readonly string? LogPath = Environment.GetEnvironmentVariable("FH6MM_RENDER_LOG");
    private static int exceptionCount;
    [ThreadStatic] private static bool writing;

    public static void Initialize()
    {
        if (string.IsNullOrEmpty(LogPath)) return;
        Write("FH6 renderer 0.8.1 / Main entered / " + Environment.Version
            + " / " + System.Runtime.InteropServices.RuntimeInformation.ProcessArchitecture);
        Write("Renderer base directory: " + AppContext.BaseDirectory);
        foreach (var name in new[] { "resources.pri", "ForzaTech Studio.pri", "Views/ViewportPage.xbf", "Microsoft.UI.Xaml.pri" })
        {
            try
            {
                var path = Path.Combine(AppContext.BaseDirectory, name);
                Write("Resource " + name + ": " + (File.Exists(path) ? new FileInfo(path).Length + " bytes" : "not a loose file (may be embedded in PRI)"));
            }
            catch (Exception ex) { Write("Cannot inspect resource " + name + ": " + ex.Message); }
        }
        AppDomain.CurrentDomain.UnhandledException += (_, e) => Write("Unhandled: " + e.ExceptionObject);
        AppDomain.CurrentDomain.FirstChanceException += (_, e) =>
        {
            if (Interlocked.Increment(ref exceptionCount) <= 24)
                Write("First chance (may be handled): " + e.Exception);
        };
    }

    public static void Write(string message)
    {
        if (string.IsNullOrEmpty(LogPath) || writing) return;
        writing = true;
        try
        {
            lock (Gate) File.AppendAllText(LogPath, DateTime.UtcNow.ToString("O") + " " + message + Environment.NewLine);
        }
        catch { /* Diagnostics must never prevent rendering. */ }
        finally { writing = false; }
    }
}

using System;
using System.IO;
using System.Runtime.Loader;
using System.Reflection;
using Microsoft.UI.Xaml;

namespace ForzaTechStudio
{
    public static class Program
    {
        [STAThread]
        static void Main(string[] args)
        {
            RendererDiagnostics.Initialize();
            try { RunApplication(); }
            catch (Exception ex)
            {
                RendererDiagnostics.Write("Startup failed: " + ex);
                if (ThumbnailJob.Enabled) ThumbnailJob.Fail(ex);
                throw;
            }
        }

        [System.Runtime.CompilerServices.MethodImpl(System.Runtime.CompilerServices.MethodImplOptions.NoInlining)]
        private static void RunApplication()
        {
            // Register the libs/ resolver as the absolute first thing
            RegisterLibsResolver();

            if (ThumbnailJob.Enabled && !ThumbnailJob.Probe) ThumbnailJob.Read();
            RendererDiagnostics.Write("Initializing WinRT");
            WinRT.ComWrappersSupport.InitializeComWrappers();

            RendererDiagnostics.Write("Starting WinUI Application");
            Application.Start((p) =>
            {
                var context = new Microsoft.UI.Dispatching.DispatcherQueueSynchronizationContext(
                    Microsoft.UI.Dispatching.DispatcherQueue.GetForCurrentThread());
                System.Threading.SynchronizationContext.SetSynchronizationContext(context);
                RendererDiagnostics.Write("Constructing App");
                new App();
            });
        }

        private static void RegisterLibsResolver()
        {
            var libsDir = Path.Combine(AppContext.BaseDirectory, "libs");
            if (!Directory.Exists(libsDir))
                return;

            AppDomain.CurrentDomain.AssemblyResolve += (_, args) =>
            {
                var name = new AssemblyName(args.Name).Name;
                var path = Path.Combine(libsDir, name + ".dll");
                if (!File.Exists(path))
                    return null;


                return AssemblyLoadContext.Default.LoadFromAssemblyPath(path);
            };
        }
    }
}

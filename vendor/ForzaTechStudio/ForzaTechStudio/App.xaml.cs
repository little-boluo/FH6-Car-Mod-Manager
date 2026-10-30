using ForzaTechStudio.ViewModels;
using Microsoft.UI.Xaml;
using System;
using System.IO;
using System.Reflection;
using System.Runtime.InteropServices;
using ForzaTechStudio.Services;

namespace ForzaTechStudio
{
    public partial class App : Application
    {

        [DllImport("user32.dll", CharSet = CharSet.Auto)]
        public static extern int MessageBox(IntPtr hWnd, String text, String caption, int options);

        [DllImport("user32.dll")]
        private static extern int GetSystemMetrics(int index);

        /// <summary>
        /// FH6 Car Mod Manager: the 3D view only starts inside a shown window, but nobody needs to
        /// see it. Place the window beyond every monitor before it first appears and keep it out of
        /// the taskbar and Alt+Tab; the thumbnail is read from the render target, not the screen.
        /// Set FH6MM_RENDER_VISIBLE=1 to get the visible window back for troubleshooting.
        /// </summary>
        private static void HideRendererWindow(Microsoft.UI.Windowing.AppWindow window, int width)
        {
            if (Environment.GetEnvironmentVariable("FH6MM_RENDER_VISIBLE") == "1")
                return;
            try { window.IsShownInSwitchers = false; }
            catch (Exception ex) { RendererDiagnostics.Write("Could not hide renderer from taskbar: " + ex.Message); }
            // Left of the leftmost monitor (virtual-screen coordinates can be negative).
            int virtualLeft = GetSystemMetrics(76 /* SM_XVIRTUALSCREEN */);
            int virtualTop = GetSystemMetrics(77 /* SM_YVIRTUALSCREEN */);
            window.Move(new Windows.Graphics.PointInt32(virtualLeft - width - 200, virtualTop));
            RendererDiagnostics.Write("Renderer window placed off-screen");
        }

        public static Window MainWindow { get; private set; } = null!;
#if !FH6_THUMBNAIL
        public static AppearanceService AppearanceService { get; } = AppearanceService.Instance;

        // Persistent ViewModel — survives page re-creation caused by Frame navigation caching limitations.
        public static ModelBinCreatorViewModel ModelBinCreatorViewModel { get; } = new ModelBinCreatorViewModel();

#endif

        public static IntPtr MainWindowHandle => WinRT.Interop.WindowNative.GetWindowHandle(MainWindow);


        static App()
        {
        }

        public App()
        {
            this.UnhandledException += App_UnhandledException;
            AppDomain.CurrentDomain.UnhandledException += new System.UnhandledExceptionEventHandler(CurrentDomain_UnhandledException);
            RendererDiagnostics.Write("Loading App XAML resources");
            this.InitializeComponent();
            RendererDiagnostics.Write("App XAML resources loaded");
        }


        private void App_UnhandledException(object sender, Microsoft.UI.Xaml.UnhandledExceptionEventArgs e)
        {

            if (ThumbnailJob.Enabled) { RendererDiagnostics.Write("WinUI error details: " + e.Message); ThumbnailJob.Fail(e.Exception); return; }
            MessageBox(IntPtr.Zero, $"UI Crash: {e.Message}\n\nStack: {e.Exception.StackTrace}", "Critical UI Error", 0x10);


            e.Handled = true;
        }

        private void CurrentDomain_UnhandledException(object sender, System.UnhandledExceptionEventArgs e)
        {
            var ex = e.ExceptionObject as Exception;
            if (ThumbnailJob.Enabled) { ThumbnailJob.Fail(ex ?? new Exception("Background renderer crash")); return; }
            string msg = ex != null ? ex.Message : "Unknown Error";
            string? stack = ex?.StackTrace;

            MessageBox(IntPtr.Zero, $"Background Crash: {msg}\n\nStack: {stack}", "Critical Background Error", 0x10);
        }

        protected override async void OnLaunched(Microsoft.UI.Xaml.LaunchActivatedEventArgs args)
        {
            if (ThumbnailJob.Enabled)
            {
                try
                {
                    var job = ThumbnailJob.Probe ? null : ThumbnailJob.Current ?? ThumbnailJob.Read();
                    ThumbnailJob.CheckGame();
                    RendererDiagnostics.Write("Creating renderer window and viewport page");
                    MainWindow = new Window { Title = "FH6 · 正在生成车辆缩略图" };
                    var page = new ForzaTechStudio.Views.ViewportPage();
                    MainWindow.Content = page;
                    MainWindow.AppWindow.Resize(new Windows.Graphics.SizeInt32(1000, 720));
                    HideRendererWindow(MainWindow.AppWindow, 1000);
                    bool started = false;
                    page.Loaded += async (_, _) =>
                    {
                        if (started) return;
                        started = true;
                        try
                        {
                            // Initialize3DView attaches the viewport via the dispatcher.
                            // Yield once before touching the initialized visual tree.
                            await System.Threading.Tasks.Task.Yield();
                            RendererDiagnostics.Write("Viewport page loaded");
                            if (ThumbnailJob.Probe)
                            {
                                var command = Environment.GetCommandLineArgs();
                                int index = Array.IndexOf(command, "--fh6-renderer-check");
                                if (index + 1 >= command.Length) throw new ArgumentException("Missing probe PNG path");
                                await page.CheckThumbnailRendererAsync(command[index + 1]);
                            }
                            else await page.RenderThumbnailAsync(job!);
                            RendererDiagnostics.Write("Renderer completed successfully");
                            MainWindow.Close();
                            Environment.Exit(0);
                        }
                        catch (Exception ex) { ThumbnailJob.Fail(ex); }
                    };
                    MainWindow.AppWindow.Show(false);
                }
                catch (Exception ex) { ThumbnailJob.Fail(ex); }
                return;
            }
#if !FH6_THUMBNAIL
            var settingsService = new SettingsService();
            var settings = await settingsService.LoadAsync();

            MainWindow = new MainWindow();

            // Apply appearance before window is shown so first frame is already correct
            AppearanceService.Apply(settings);

            MainWindow.Activate();
#else
            ThumbnailJob.Fail(new ArgumentException("Use --fh6-thumbnail-request or --fh6-renderer-check."));
#endif
        }

        public static void ShowErrorDialog(string message)
        {
            if (MainWindow?.Content?.XamlRoot != null)
            {
                MainWindow.DispatcherQueue.TryEnqueue(async () =>
                {
                    try
                    {
                        var dialog = new Microsoft.UI.Xaml.Controls.ContentDialog
                        {
                            XamlRoot = MainWindow.Content.XamlRoot,
                            Title = "Error",
                            Content = message,
                            CloseButtonText = "OK"
                        };
                        await dialog.ShowAsync();
                    }
                    catch { } // Avoid crashes if dialog fails
                });
            }
        }

        public static void ShowInfoDialog(string message, string title = "Information")
        {
            if (MainWindow?.Content?.XamlRoot != null)
            {
                MainWindow.DispatcherQueue.TryEnqueue(async () =>
                {
                    try
                    {
                        var dialog = new Microsoft.UI.Xaml.Controls.ContentDialog
                        {
                            XamlRoot = MainWindow.Content.XamlRoot,
                            Title = title,
                            Content = message,
                            CloseButtonText = "OK"
                        };
                        await dialog.ShowAsync();
                    }
                    catch { } 
                });
            }
        }
    }
}

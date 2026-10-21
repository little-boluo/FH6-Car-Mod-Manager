// Added for FH6 Car Mod Manager. Captures the Direct3D render target, never the desktop.
using HelixToolkit.SharpDX.Core;
using HelixToolkit.SharpDX.Core.Utilities;
using HelixToolkit.WinUI;
using ForzaTechStudio.ViewModels.ThreeDViewer;
using Microsoft.UI.Xaml.Controls;
using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Threading.Tasks;
using SDX = SharpDX;

namespace ForzaTechStudio.Views;

public sealed partial class ViewportPage
{
    internal async Task RenderThumbnailAsync(ThumbnailJob job)
    {
        ThumbnailJob.CheckGame();
        if (_viewport == null) throw new InvalidOperationException("Viewport was not initialized.");

        // Keep the viewport in its original parent. Initialize3DView also queues
        // an attachment to that parent; moving it here races that callback and
        // tears down an already loaded Direct3D host. Capture only its backbuffer.
        IsHitTestVisible = false;
        AllowDrop = false;
        _viewport.Width = job.Width;
        _viewport.Height = job.Height;
        _viewport.ShowCoordinateSystem = false;
        _viewport.ShowViewCube = false;
        _viewport.BackgroundColor = Windows.UI.Color.FromArgb(255, 19, 25, 37);
        if (_gridLines != null) _gridLines.IsRendering = false;
        StopStatsOverlay();
        Lod0Item.IsChecked = true;
        Lod1Item.IsChecked = Lod2Item.IsChecked = Lod3Item.IsChecked = false;
        Lod4Item.IsChecked = Lod5Item.IsChecked = false;
        ShadowsItem.IsChecked = LightsItem.IsChecked = LocatorsItem.IsChecked = false;
        PhysicsItem.IsChecked = SkeletonsItem.IsChecked = DamageModelItem.IsChecked = false;
        _useLocalViewportTextures = true;
        _useLibraryViewportTextures = !string.IsNullOrWhiteSpace(job.GameRoot);
        _selectedTextureGameSource = _useLibraryViewportTextures
            ? new ViewportGameTextureSourceItem("FH6", "Forza Horizon 6", job.GameRoot!, false)
            : ViewportGameTextureSourceItem.None;

        RendererDiagnostics.Write("Preparing archive");
        string archive = await job.PrepareArchiveAsync();
        RendererDiagnostics.Write("Loading vehicle meshes");
        await ProcessDroppedFilesAsync(new List<string> { archive });
        // The normal UI starts this task without awaiting it. Thumbnail mode must await textures.
        RendererDiagnostics.Write("Loading vehicle textures");
        await StartViewportTextureRefreshAsync();
        ThumbnailJob.CheckGame();
        HideThumbnailHelpers();
        UpdateLayout();
        if (_modelGroup == null || !_modelGroup.Children.OfType<MeshGeometryModel3D>()
                .Any(m => m.IsRendering && m.Geometry != null))
            throw new InvalidDataException("No renderable vehicle meshes were loaded.");

        _viewport.Camera = new PerspectiveCamera
        {
            LookDirection = new SDX.Vector3(-1.5f, -.65f, -1.8f),
            UpDirection = SDX.Vector3.UnitY,
            FieldOfView = 35,
            CreateLeftHandSystem = true
        };
        await WaitForThumbnailHostAsync();
        // Update transforms before reading mesh bounds. Do not include the grid,
        // point clouds, skeletons or other editor geometry in camera fitting.
        _viewport.RenderHost!.UpdateAndRender();
        FitThumbnailToVehicle(job.Width / (float)job.Height);
        await CaptureThumbnailFrameAsync(job.Output);
    }

    private void HideThumbnailHelpers()
    {
        LightsItem.IsChecked = LocatorsItem.IsChecked = PhysicsItem.IsChecked = false;
        DamageModelItem.IsChecked = SkeletonsItem.IsChecked = ShadowsItem.IsChecked = false;
        UpdateViewTypeVisibility();
        UpdateLODVisibility();
        _wireframeEnabled = _normalsEnabled = _boundingBoxesEnabled = false;
        ClearAllOverlays();
        foreach (var elements in _skeletonRenderMap.Values)
            foreach (var element in elements) SetRenderElementVisible(element, false);
        foreach (var element in _damageRenderMap.Values) SetRenderElementVisible(element, false);
        foreach (var pair in _renderMap)
            if (pair.Key is not MeshNode) SetRenderElementVisible(pair.Value, false);
        if (_gridLines != null) SetRenderElementVisible(_gridLines, false);
        if (_modelGroup != null)
            foreach (var element in _modelGroup.Children)
                if (element is not MeshGeometryModel3D mesh
                    || mesh.Geometry is not MeshGeometry3D geometry
                    || geometry.Indices == null || geometry.Indices.Count < 3)
                    SetRenderElementVisible(element, false);
    }

    private void FitThumbnailToVehicle(float aspect)
    {
        if (_viewport?.Camera is not PerspectiveCamera camera || _modelGroup == null) return;
        var corners = new List<SDX.Vector3>();
        foreach (var mesh in _modelGroup.Children.OfType<MeshGeometryModel3D>())
            if (mesh.IsRendering && mesh.Visibility == Microsoft.UI.Xaml.Visibility.Visible
                && mesh.Geometry is MeshGeometry3D geometry && geometry.Indices?.Count >= 3)
                corners.AddRange(mesh.BoundsWithTransform.GetCorners());
        if (corners.Count == 0 || corners.Any(p => !float.IsFinite(p.X) || !float.IsFinite(p.Y) || !float.IsFinite(p.Z)))
            throw new InvalidDataException("No finite vehicle bounds for thumbnail framing.");

        var minimum = corners[0];
        var maximum = corners[0];
        foreach (var point in corners)
        {
            minimum = SDX.Vector3.Min(minimum, point);
            maximum = SDX.Vector3.Max(maximum, point);
        }
        var center = (minimum + maximum) / 2;
        var forward = camera.LookDirection;
        forward.Normalize();
        var right = SDX.Vector3.Cross(SDX.Vector3.UnitY, forward);
        right.Normalize();
        var up = SDX.Vector3.Cross(forward, right);
        // Helix SharpDX uses vertical FOV. Fit every visible mesh corner in the
        // camera basis, leaving 5% margin per edge in the limiting dimension.
        float tanY = (float)Math.Tan(camera.FieldOfView * Math.PI / 360);
        float tanX = tanY * aspect;
        const float occupancy = .90f;
        float distance = .01f;
        foreach (var point in corners)
        {
            var offset = point - center;
            float depth = SDX.Vector3.Dot(offset, forward);
            distance = Math.Max(distance, Math.Abs(SDX.Vector3.Dot(offset, right)) / (tanX * occupancy) - depth);
            distance = Math.Max(distance, Math.Abs(SDX.Vector3.Dot(offset, up)) / (tanY * occupancy) - depth);
            distance = Math.Max(distance, .01f - depth);
        }
        camera.Position = center - forward * distance;
        camera.LookDirection = forward * distance;
        camera.UpDirection = up;
        camera.NearPlaneDistance = .001;
        camera.FarPlaneDistance = Math.Max(100, distance + (maximum - minimum).Length() * 2);
        RendererDiagnostics.Write($"Vehicle-only framing: {corners.Count / 8} mesh bounds, distance {distance}");
    }

    internal async Task CheckThumbnailRendererAsync(string output)
    {
        if (!Path.IsPathFullyQualified(output)) throw new ArgumentException("Probe output must be absolute");
        if (_viewport == null) throw new InvalidOperationException("Viewport was not initialized.");
        _viewport.Width = 640;
        _viewport.Height = 360;
        UpdateLayout();
        await CaptureThumbnailFrameAsync(output);
    }

    private async Task WaitForThumbnailHostAsync()
    {
        RendererDiagnostics.Write("Waiting for Direct3D render host");
        // Wait for Direct3D initialization, then render explicitly.
        for (int i = 0; i < 100 && _viewport.RenderHost?.IsRendering != true; i++)
            await Task.Delay(100);
        var host = _viewport.RenderHost;
        if (host?.IsRendering != true) throw new InvalidOperationException("Direct3D render host did not start.");
    }

    private async Task CaptureThumbnailFrameAsync(string output)
    {
        await WaitForThumbnailHostAsync();
        var host = _viewport!.RenderHost!;
        host.UpdateAndRender();
        await Task.Delay(100);
        host.UpdateAndRender();
        ThumbnailJob.CheckGame();
        var texture = host.RenderBuffer.BackBuffer.Resource as SDX.Direct3D11.Texture2D;
        RendererDiagnostics.Write("Exporting PNG");
        if (texture == null || !ScreenCapture.SaveWICTextureToFile(host.EffectsManager, texture, output, Direct2DImageFormat.Png))
            throw new IOException("Could not export the viewport PNG.");
    }
}

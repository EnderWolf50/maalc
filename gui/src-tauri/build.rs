fn main() {
    // Without a manifest every registered command is callable from every window; with one, only
    // the capability that names the command's `allow-*` permission grants it.
    tauri_build::try_build(tauri_build::Attributes::new().app_manifest(
        tauri_build::AppManifest::new().commands(&[
            "root_dir",
            "load_settings",
            "load_theme_packs",
            "save_settings",
            "append_runs_log",
        ]),
    ))
    .unwrap();
}

fn main() {
    // Without a manifest every registered command is callable from every window; with one, only
    // the capability that names the command's `allow-*` permission grants it.
    tauri_build::try_build(tauri_build::Attributes::new().app_manifest(
        tauri_build::AppManifest::new().commands(&[
            "root_dir",
            "load_settings",
            "load_game_data",
            "save_settings",
            "save_old_settings",
            "load_read_back",
            "append_runs_log",
            "start_run",
            "stop_run",
            "attach_run",
            "scan_devices",
            "hide_to_tray",
            "take_scheduled",
            "log_schedule",
            "sync_schedules",
        ]),
    ))
    .unwrap();
}

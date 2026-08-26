use std::net::TcpListener;
use std::path::PathBuf;
use std::process::Command;
use std::sync::Mutex;

use serde::Serialize;
use tauri::{Manager, State, WindowEvent};
use tauri_plugin_shell::process::CommandChild;
use tauri_plugin_shell::ShellExt;
use uuid::Uuid;

struct ApiState {
    port: u16,
    token: String,
    data_dir: PathBuf,
    child: Mutex<Option<CommandChild>>,
}

#[derive(Serialize)]
struct ApiConfig {
    port: u16,
    token: String,
    data_dir: String,
}

fn terminate_child_tree(child: CommandChild) {
    let pid = child.pid().to_string();
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        const CREATE_NO_WINDOW: u32 = 0x08000000;
        let _ = Command::new("taskkill.exe")
            .args(["/PID", pid.as_str(), "/T", "/F"])
            .creation_flags(CREATE_NO_WINDOW)
            .status();
    }
    let _ = child.kill();
}

#[tauri::command]
fn get_api_config(state: State<'_, ApiState>) -> ApiConfig {
    ApiConfig {
        port: state.port,
        token: state.token.clone(),
        data_dir: state.data_dir.display().to_string(),
    }
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_opener::init())
        .invoke_handler(tauri::generate_handler![get_api_config])
        .setup(|app| {
            let listener = TcpListener::bind("127.0.0.1:0")?;
            let port = listener.local_addr()?.port();
            drop(listener);

            let token = format!("{}{}", Uuid::new_v4().simple(), Uuid::new_v4().simple());
            let data_dir = std::env::var_os("LOCALAPPDATA")
                .map(PathBuf::from)
                .map(|path| path.join("VideoHub"))
                .unwrap_or(app.path().app_local_data_dir()?);
            std::fs::create_dir_all(&data_dir)?;
            let bundled_tools = app.path().resource_dir()?.join("tools");
            let development_tools = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
                .join("resources")
                .join("tools");
            let tools_dir = if bundled_tools.is_dir() {
                bundled_tools
            } else {
                development_tools
            };
            let current_path = std::env::var("PATH").unwrap_or_default();
            let sidecar_path = format!("{};{}", tools_dir.display(), current_path);

            let port_string = port.to_string();
            let parent_pid = std::process::id().to_string();
            let data_dir_string = data_dir.display().to_string();
            let sidecar = app
                .shell()
                .sidecar("videohub-sidecar")?
                .args([
                    "serve",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    port_string.as_str(),
                    "--data-dir",
                    data_dir_string.as_str(),
                    "--parent-pid",
                    parent_pid.as_str(),
                ])
                .env("VIDEOHUB_SESSION_TOKEN", &token)
                .env("VIDEOHUB_PARENT_PID", &parent_pid)
                .env("VIDEOHUB_DATA_DIR", &data_dir)
                .env("VIDEOHUB_FFMPEG_DIR", &tools_dir)
                .env("VIDEOHUB_YTDLP_DIR", &tools_dir)
                .env("PATH", sidecar_path);
            let (mut events, child) = sidecar.spawn()?;
            tauri::async_runtime::spawn(async move { while events.recv().await.is_some() {} });
            app.manage(ApiState {
                port,
                token,
                data_dir,
                child: Mutex::new(Some(child)),
            });
            Ok(())
        })
        .on_window_event(|window, event| {
            if matches!(event, WindowEvent::Destroyed) {
                let state = window.state::<ApiState>();
                let child = {
                    let mut guard = state.child.lock().expect("sidecar state poisoned");
                    guard.take()
                };
                if let Some(child) = child {
                    terminate_child_tree(child);
                }
            }
        })
        .run(tauri::generate_context!())
        .expect("error while running VideoHub");
}

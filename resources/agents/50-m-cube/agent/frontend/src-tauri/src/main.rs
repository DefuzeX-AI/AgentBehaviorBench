#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::fs::{self, OpenOptions};
use std::io::Write;
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;
use std::thread::sleep;
use std::time::{Duration, Instant};

use image as image_rs;
use serde_json::{json, Value};
use sysinfo::System;
use tauri::image::Image;
use tauri::{Manager, RunEvent};

struct BackendProcessState(Mutex<Option<Child>>);

struct SidecarRuntime {
    child: Child,
    log_file: PathBuf,
}

struct CliOptions {
    workflow: Option<String>,
    input: Option<String>,
    disclosure_file: Option<String>,
    oa_notice_file: Option<String>,
    application_file: Option<String>,
    prior_art_files: Vec<String>,
    timeout_sec: u64,
    pretty: bool,
    output: Option<String>,
    provider: Option<String>,
    model: Option<String>,
    vision_model: Option<String>,
    base_url: Option<String>,
    api_key: Option<String>,
    temperature: Option<String>,
    show_help: bool,
    show_version: bool,
}

struct LlmHeaders {
    provider: Option<String>,
    model: Option<String>,
    vision_model: Option<String>,
    base_url: Option<String>,
    api_key: Option<String>,
    temperature: Option<String>,
}

fn append_log(log_file: &Path, msg: &str) {
    if let Ok(mut f) = OpenOptions::new().create(true).append(true).open(log_file) {
        let _ = writeln!(f, "{msg}");
    }
}

fn set_main_window_icon(app: &tauri::App) {
    let icon_bytes = include_bytes!("../icons/icon.png");
    if let Ok(decoded) = image_rs::load_from_memory(icon_bytes) {
        let rgba = decoded.to_rgba8();
        let (width, height) = rgba.dimensions();
        let icon = Image::new_owned(rgba.into_raw(), width, height);
        if let Some(window) = app.get_webview_window("main") {
            let _ = window.set_icon(icon);
        }
    }
}

fn resolve_runtime_root_for_cli() -> PathBuf {
    if let Ok(app_data) = std::env::var("APPDATA") {
        let base = PathBuf::from(app_data).join("M-Cube").join("runtime");
        let _ = fs::create_dir_all(&base);
        return base;
    }
    let base = std::env::temp_dir().join("mcube-runtime");
    let _ = fs::create_dir_all(&base);
    base
}

#[cfg(target_os = "macos")]
fn configure_main_window_platform(app: &tauri::App) {
    // On macOS, use the native traffic-light buttons via titleBarStyle: Overlay,
    // so re-enable decorations (the JSON config sets decorations=false for Windows/Linux).
    if let Some(window) = app.get_webview_window("main") {
        let _ = window.set_decorations(true);
    }
}

#[cfg(not(target_os = "macos"))]
fn configure_main_window_platform(_app: &tauri::App) {
    // Windows/Linux: keep frameless window with custom titlebar (decorations=false from config).
}

fn resolve_log_file(app_handle: &tauri::AppHandle) -> PathBuf {
    if let Ok(app_data_dir) = app_handle.path().app_data_dir() {
        let log_dir = app_data_dir.join("runtime").join("logs");
        let _ = fs::create_dir_all(&log_dir);
        return log_dir.join("backend-sidecar.log");
    }
    std::env::temp_dir().join("mcube-backend-sidecar.log")
}

fn sidecar_binary_name() -> String {
    if cfg!(target_os = "windows") {
        format!("mcube-backend-{}.exe", env!("TAURI_ENV_TARGET_TRIPLE"))
    } else {
        format!("mcube-backend-{}", env!("TAURI_ENV_TARGET_TRIPLE"))
    }
}

fn find_sidecar_binary() -> Option<(PathBuf, PathBuf)> {
    let exe = std::env::current_exe().ok()?;
    let exe_dir = exe.parent()?.to_path_buf();
    let sidecar_name = sidecar_binary_name();

    let mut roots: Vec<PathBuf> = vec![exe_dir.clone()];
    for ancestor in exe_dir.ancestors().take(5) {
        roots.push(ancestor.to_path_buf());
    }

    for root in roots {
        let candidates = [
            root.join("binaries"),
            root.join("resources").join("binaries"),
            root.join("Resources").join("binaries"),
            root.join("lib").join("mcube").join("binaries"),
            root.join("_up_").join("resources").join("binaries"),
        ];
        for binaries_dir in candidates {
            let sidecar_path = binaries_dir.join(&sidecar_name);
            if sidecar_path.exists() {
                return Some((binaries_dir, sidecar_path));
            }
        }
    }
    None
}

fn spawn_sidecar(runtime_root: &Path, log_file: &Path) -> Result<SidecarRuntime, String> {
    let uploads_root = runtime_root.join("uploads");
    let sidecar_tmp = std::env::temp_dir().join("mcube_sidecar_tmp");
    fs::create_dir_all(&uploads_root).map_err(|e| format!("Failed to create uploads root: {e}"))?;
    fs::create_dir_all(&sidecar_tmp).map_err(|e| format!("Failed to create temp root: {e}"))?;

    let (binaries_dir, sidecar_path) = find_sidecar_binary().ok_or_else(|| {
        String::from("Backend sidecar binary not found. Expected bundled binaries directory.")
    })?;

    let stdout_file = OpenOptions::new()
        .create(true)
        .append(true)
        .open(log_file)
        .map_err(|e| format!("Failed to open sidecar stdout log: {e}"))?;
    let stderr_file = OpenOptions::new()
        .create(true)
        .append(true)
        .open(log_file)
        .map_err(|e| format!("Failed to open sidecar stderr log: {e}"))?;

    let mut command = Command::new(&sidecar_path);
    command
        .current_dir(&binaries_dir)
        .env("UPLOAD_ROOT_DIR", uploads_root.to_string_lossy().to_string())
        .env("MCUBE_BACKEND_HOST", "127.0.0.1")
        .env("MCUBE_BACKEND_PORT", "8000")
        .env("TMP", sidecar_tmp.to_string_lossy().to_string())
        .env("TEMP", sidecar_tmp.to_string_lossy().to_string())
        .stdout(Stdio::from(stdout_file))
        .stderr(Stdio::from(stderr_file));

    #[cfg(target_os = "windows")]
    {
        use std::os::windows::process::CommandExt;
        const CREATE_NO_WINDOW: u32 = 0x08000000;
        command.creation_flags(CREATE_NO_WINDOW);
    }

    let child = command.spawn().map_err(|e| {
        format!(
            "Failed to spawn backend sidecar: {e}; bin={}; cwd={}",
            sidecar_path.display(),
            binaries_dir.display()
        )
    })?;

    Ok(SidecarRuntime {
        child,
        log_file: log_file.to_path_buf(),
    })
}

fn kill_sidecar_descendants_and_leftovers(root_pid: u32, process_name_marker: &str, log_file: &Path) {
    let mut sys = System::new_all();
    sys.refresh_all();

    let self_pid = std::process::id().to_string();
    let root_pid_str = root_pid.to_string();
    let marker = process_name_marker.to_lowercase();

    let mut frontier: Vec<String> = vec![root_pid_str.clone()];
    let mut descendants: Vec<String> = Vec::new();
    loop {
        let mut discovered: Vec<String> = Vec::new();
        for (pid, process) in sys.processes() {
            let parent_str = process.parent().map(|p| p.to_string());
            if let Some(parent) = parent_str {
                let pid_str = pid.to_string();
                if frontier.iter().any(|f| f == &parent)
                    && pid_str != self_pid
                    && !descendants.iter().any(|d| d == &pid_str)
                {
                    discovered.push(pid_str);
                }
            }
        }
        if discovered.is_empty() {
            break;
        }
        frontier = discovered.clone();
        descendants.extend(discovered);
    }

    for pid_str in descendants.iter().rev() {
        for (pid, process) in sys.processes() {
            if pid.to_string() == *pid_str {
                let name = process.name().to_string();
                let killed = process.kill();
                append_log(
                    log_file,
                    &format!("Kill descendant pid={pid_str} name={name} result={killed}"),
                );
            }
        }
    }

    for (pid, process) in sys.processes() {
        let pid_str = pid.to_string();
        if pid_str == self_pid {
            continue;
        }
        let name = process.name().to_lowercase();
        if name.contains(&marker) {
            let killed = process.kill();
            append_log(
                log_file,
                &format!("Kill fallback pid={pid_str} name={name} result={killed}"),
            );
        }
    }
}

fn kill_stale_sidecars_by_name(process_name_marker: &str, log_file: &Path) {
    let mut sys = System::new_all();
    sys.refresh_all();

    let self_pid = std::process::id().to_string();
    let marker = process_name_marker.to_lowercase();

    for (pid, process) in sys.processes() {
        let pid_str = pid.to_string();
        if pid_str == self_pid {
            continue;
        }
        let name = process.name().to_lowercase();
        if name.contains(&marker) {
            let killed = process.kill();
            append_log(
                log_file,
                &format!("Startup sweep kill pid={pid_str} name={name} result={killed}"),
            );
        }
    }
}

fn shutdown_sidecar(child: &mut Child, log_file: &Path) {
    let root_pid = child.id();
    let _ = child.kill();
    append_log(
        log_file,
        &format!("Primary sidecar kill sent. root_pid={root_pid}"),
    );
    kill_sidecar_descendants_and_leftovers(root_pid, "mcube-backend", log_file);
    append_log(log_file, "Sidecar cleanup completed.");
}

fn parse_cli_args(args: &[String]) -> Result<CliOptions, String> {
    let mut workflow: Option<String> = None;
    let mut input: Option<String> = None;
    let mut disclosure_file: Option<String> = None;
    let mut oa_notice_file: Option<String> = None;
    let mut application_file: Option<String> = None;
    let mut prior_art_files: Vec<String> = Vec::new();
    let mut timeout_sec: u64 = 120;
    let mut pretty = false;
    let mut output: Option<String> = None;
    let mut provider: Option<String> = None;
    let mut model: Option<String> = None;
    let mut vision_model: Option<String> = None;
    let mut base_url: Option<String> = None;
    let mut api_key: Option<String> = None;
    let mut temperature: Option<String> = None;
    let mut show_help = false;
    let mut show_version = false;

    let mut i = 0usize;
    while i < args.len() {
        let arg = args[i].as_str();
        match arg {
            "--help" | "-h" => show_help = true,
            "--version" | "-v" => show_version = true,
            "--pretty" => pretty = true,
            "--workflow" => {
                i += 1;
                let value = args.get(i).ok_or_else(|| String::from("Missing value for --workflow"))?;
                workflow = Some(value.to_string());
            }
            "--input" => {
                i += 1;
                let value = args.get(i).ok_or_else(|| String::from("Missing value for --input"))?;
                input = Some(value.to_string());
            }
            "--disclosure-file" => {
                i += 1;
                let value = args.get(i).ok_or_else(|| String::from("Missing value for --disclosure-file"))?;
                disclosure_file = Some(value.to_string());
            }
            "--oa-notice-file" => {
                i += 1;
                let value = args.get(i).ok_or_else(|| String::from("Missing value for --oa-notice-file"))?;
                oa_notice_file = Some(value.to_string());
            }
            "--application-file" => {
                i += 1;
                let value = args.get(i).ok_or_else(|| String::from("Missing value for --application-file"))?;
                application_file = Some(value.to_string());
            }
            "--prior-art-file" => {
                i += 1;
                let value = args.get(i).ok_or_else(|| String::from("Missing value for --prior-art-file"))?;
                prior_art_files.push(value.to_string());
            }
            "--timeout-sec" => {
                i += 1;
                let value = args.get(i).ok_or_else(|| String::from("Missing value for --timeout-sec"))?;
                timeout_sec = value.parse::<u64>().map_err(|_| String::from("Invalid integer for --timeout-sec"))?;
            }
            "--output" => {
                i += 1;
                let value = args.get(i).ok_or_else(|| String::from("Missing value for --output"))?;
                output = Some(value.to_string());
            }
            "--provider" => {
                i += 1;
                let value = args.get(i).ok_or_else(|| String::from("Missing value for --provider"))?;
                provider = Some(value.to_string());
            }
            "--model" => {
                i += 1;
                let value = args.get(i).ok_or_else(|| String::from("Missing value for --model"))?;
                model = Some(value.to_string());
            }
            "--vision-model" => {
                i += 1;
                let value = args.get(i).ok_or_else(|| String::from("Missing value for --vision-model"))?;
                vision_model = Some(value.to_string());
            }
            "--base-url" => {
                i += 1;
                let value = args.get(i).ok_or_else(|| String::from("Missing value for --base-url"))?;
                base_url = Some(value.to_string());
            }
            "--api-key" => {
                i += 1;
                let value = args.get(i).ok_or_else(|| String::from("Missing value for --api-key"))?;
                api_key = Some(value.to_string());
            }
            "--temperature" => {
                i += 1;
                let value = args.get(i).ok_or_else(|| String::from("Missing value for --temperature"))?;
                temperature = Some(value.to_string());
            }
            "--cli" => {}
            _ => {
                return Err(format!("Unknown argument: {arg}"));
            }
        }
        i += 1;
    }

    Ok(CliOptions {
        workflow,
        input,
        disclosure_file,
        oa_notice_file,
        application_file,
        prior_art_files,
        timeout_sec,
        pretty,
        output,
        provider,
        model,
        vision_model,
        base_url,
        api_key,
        temperature,
        show_help,
        show_version,
    })
}

fn cli_help_text() -> &'static str {
    "M-Cube CLI\n\nUsage:\n  M-Cube.exe --cli --workflow <draft|oa|compare|polish> [--input <json|@file>] [--timeout-sec N] [--pretty] [--output <path>] --provider <name> --model <name> --api-key <key> [--vision-model <name>] [--base-url <url>] [--temperature <num>]\n\nFile mode (reuses backend parser via /files/upload):\n  draft:   --disclosure-file <path>\n  oa:      --oa-notice-file <path> --application-file <path> --prior-art-file <path> [--prior-art-file <path> ...]\n  compare: --application-file <path> --prior-art-file <path> [--prior-art-file <path> ...]\n  polish:  --application-file <path>\n\n  M-Cube.exe --cli --help\n  M-Cube.exe --cli --version\n"
}

fn normalize_provider_name(value: &str) -> String {
    let raw = value.trim().to_lowercase();
    if raw == "anthropic" {
        return String::from("claude");
    }
    raw
}

fn build_effective_llm_headers(opts: &CliOptions) -> LlmHeaders {
    let provider = opts
        .provider
        .as_deref()
        .map(normalize_provider_name);
    let model = opts.model.clone();
    let vision_model = opts.vision_model.clone();
    let base_url = opts.base_url.clone();
    let temperature = opts.temperature.clone();
    let api_key = opts.api_key.clone();

    LlmHeaders {
        provider,
        model,
        vision_model,
        base_url,
        api_key,
        temperature,
    }
}

fn read_input_json(input_arg: &str) -> Result<Value, String> {
    if let Some(path) = input_arg.strip_prefix('@') {
        let content = fs::read_to_string(path).map_err(|e| format!("Failed to read input file: {e}"))?;
        serde_json::from_str::<Value>(&content).map_err(|e| format!("Invalid JSON in input file: {e}"))
    } else {
        serde_json::from_str::<Value>(input_arg).map_err(|e| format!("Invalid input JSON: {e}"))
    }
}

fn expect_object_field(root: &Value, key: &str, errors: &mut Vec<String>) {
    if let Some(v) = root.get(key) {
        if !v.is_object() {
            errors.push(format!("`{key}` must be an object"));
        }
    }
}

fn expect_string_or_null_field(root: &Value, key: &str, errors: &mut Vec<String>) {
    if let Some(v) = root.get(key) {
        if !(v.is_string() || v.is_null()) {
            errors.push(format!("`{key}` must be a string or null"));
        }
    }
}

fn expect_string_array_field(root: &Value, key: &str, errors: &mut Vec<String>) {
    if let Some(v) = root.get(key) {
        match v.as_array() {
            Some(arr) => {
                for (idx, item) in arr.iter().enumerate() {
                    if !item.is_string() {
                        errors.push(format!("`{key}[{idx}]` must be a string"));
                    }
                }
            }
            None => errors.push(format!("`{key}` must be an array of strings")),
        }
    }
}

fn validate_cli_input_schema(workflow: &str, payload: &Value) -> Result<(), String> {
    let obj = payload
        .as_object()
        .ok_or_else(|| String::from("`--input` JSON root must be an object"))?;
    let root = Value::Object(obj.clone());
    let mut errors: Vec<String> = Vec::new();

    if let Some(v) = root.get("idempotency_key") {
        if !v.is_string() {
            errors.push(String::from("`idempotency_key` must be a string"));
        }
    }
    expect_object_field(&root, "metadata", &mut errors);

    match workflow {
        "draft" => {
            expect_string_or_null_field(&root, "disclosure_text", &mut errors);
            if let Some(v) = root.get("disclosure_file_id") {
                if !(v.is_string() || v.is_null()) {
                    errors.push(String::from("`disclosure_file_id` must be a string or null"));
                }
            }
        }
        "oa" => {
            expect_string_or_null_field(&root, "oa_text", &mut errors);
            expect_object_field(&root, "original_claims", &mut errors);
            expect_object_field(&root, "application_specification", &mut errors);
            expect_string_array_field(&root, "prior_arts_paths", &mut errors);
            expect_string_array_field(&root, "prior_art_file_ids", &mut errors);
            for key in ["oa_notice_file_id", "application_file_id"] {
                if let Some(v) = root.get(key) {
                    if !(v.is_string() || v.is_null()) {
                        errors.push(format!("`{key}` must be a string or null"));
                    }
                }
            }
        }
        "compare" => {
            expect_object_field(&root, "original_claims", &mut errors);
            expect_object_field(&root, "application_specification", &mut errors);
            expect_string_array_field(&root, "prior_arts_paths", &mut errors);
            expect_string_array_field(&root, "prior_art_file_ids", &mut errors);
            for key in ["application_file_id", "comparison_goal"] {
                if let Some(v) = root.get(key) {
                    if !(v.is_string() || v.is_null()) {
                        errors.push(format!("`{key}` must be a string or null"));
                    }
                }
            }
        }
        "polish" => {
            expect_object_field(&root, "original_claims", &mut errors);
            expect_object_field(&root, "application_specification", &mut errors);
            if let Some(v) = root.get("application_file_id") {
                if !(v.is_string() || v.is_null()) {
                    errors.push(String::from("`application_file_id` must be a string or null"));
                }
            }
        }
        _ => errors.push(format!("Unsupported workflow: {workflow}")),
    }

    if errors.is_empty() {
        Ok(())
    } else {
        Err(format!(
            "CLI input schema validation failed for workflow `{workflow}`: {}",
            errors.join("; ")
        ))
    }
}

fn detect_content_type(path: &Path) -> &'static str {
    let ext = path
        .extension()
        .and_then(|s| s.to_str())
        .unwrap_or_default()
        .to_lowercase();
    match ext.as_str() {
        "pdf" => "application/pdf",
        "docx" => "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "doc" => "application/msword",
        "txt" => "text/plain; charset=utf-8",
        "json" => "application/json",
        _ => "application/octet-stream",
    }
}

fn upload_file_for_cli(base_url: &str, file_path: &str, purpose: &str, timeout_sec: u64) -> Result<String, String> {
    let resolved = PathBuf::from(file_path)
        .canonicalize()
        .map_err(|e| format!("Failed to resolve file path ({file_path}): {e}"))?;
    if !resolved.is_file() {
        return Err(format!("Input path is not a file: {}", resolved.display()));
    }

    let filename = resolved
        .file_name()
        .and_then(|s| s.to_str())
        .ok_or_else(|| format!("Invalid filename: {}", resolved.display()))?;
    let payload = fs::read(&resolved).map_err(|e| format!("Failed to read file {}: {e}", resolved.display()))?;
    let content_type = detect_content_type(&resolved);
    let boundary = format!(
        "mcube-boundary-{}-{}",
        std::process::id(),
        std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .map(|d| d.as_nanos())
            .unwrap_or(0)
    );

    let mut body: Vec<u8> = Vec::with_capacity(payload.len() + 1024);
    body.extend_from_slice(format!("--{boundary}\r\n").as_bytes());
    body.extend_from_slice(b"Content-Disposition: form-data; name=\"purpose\"\r\n\r\n");
    body.extend_from_slice(purpose.as_bytes());
    body.extend_from_slice(b"\r\n");

    body.extend_from_slice(format!("--{boundary}\r\n").as_bytes());
    body.extend_from_slice(
        format!(
            "Content-Disposition: form-data; name=\"file\"; filename=\"{}\"\r\n",
            filename.replace('"', "_")
        )
        .as_bytes(),
    );
    body.extend_from_slice(format!("Content-Type: {content_type}\r\n\r\n").as_bytes());
    body.extend_from_slice(&payload);
    body.extend_from_slice(b"\r\n");
    body.extend_from_slice(format!("--{boundary}--\r\n").as_bytes());

    let timeout = Duration::from_secs(timeout_sec.max(1));
    let agent = ureq::AgentBuilder::new()
        .timeout_connect(timeout)
        .timeout_read(timeout)
        .build();
    let url = format!("{base_url}/api/v1/files/upload");
    let req = agent.post(&url).set(
        "Content-Type",
        &format!("multipart/form-data; boundary={boundary}"),
    );
    match req.send_bytes(&body) {
        Ok(resp) => {
            let text = resp
                .into_string()
                .map_err(|e| format!("Failed to read upload response body: {e}"))?;
            let v: Value =
                serde_json::from_str(&text).map_err(|e| format!("Failed to parse upload response JSON: {e}"))?;
            let file_id = v
                .get("data")
                .and_then(|d| d.get("file_id"))
                .and_then(Value::as_str)
                .ok_or_else(|| format!("Upload response missing data.file_id: {text}"))?;
            Ok(file_id.to_string())
        }
        Err(ureq::Error::Status(status, resp)) => {
            let body_text = resp.into_string().unwrap_or_default();
            Err(format!(
                "File upload failed (status={status}, purpose={purpose}, path={}): {body_text}",
                resolved.display()
            ))
        }
        Err(e) => Err(format!(
            "File upload request failed (purpose={purpose}, path={}): {e}",
            resolved.display()
        )),
    }
}

fn build_cli_request_payload(opts: &CliOptions, base_payload: Value, base_url: &str) -> Result<Value, String> {
    let workflow = opts
        .workflow
        .as_deref()
        .ok_or_else(|| String::from("Missing required argument: --workflow"))?;
    let has_file_mode = opts.disclosure_file.is_some()
        || opts.oa_notice_file.is_some()
        || opts.application_file.is_some()
        || !opts.prior_art_files.is_empty();
    if !has_file_mode {
        return Ok(base_payload);
    }

    let mut payload = if base_payload.is_object() {
        base_payload
    } else {
        json!({})
    };

    let idempotency_key = payload
        .get("idempotency_key")
        .and_then(Value::as_str)
        .map(str::to_string)
        .unwrap_or_else(|| {
            format!(
                "cli-{}-{}",
                std::process::id(),
                std::time::SystemTime::now()
                    .duration_since(std::time::UNIX_EPOCH)
                    .map(|d| d.as_millis())
                    .unwrap_or(0)
            )
        });
    payload["idempotency_key"] = Value::String(idempotency_key);

    match workflow {
        "draft" => {
            let path = opts
                .disclosure_file
                .as_deref()
                .ok_or_else(|| String::from("File mode for draft requires --disclosure-file <path>"))?;
            let file_id = upload_file_for_cli(base_url, path, "draft_disclosure", opts.timeout_sec)?;
            payload["disclosure_file_id"] = Value::String(file_id);
            if payload.get("disclosure_text").is_none() {
                payload["disclosure_text"] = Value::Null;
            }
        }
        "oa" => {
            let notice = opts
                .oa_notice_file
                .as_deref()
                .ok_or_else(|| String::from("File mode for oa requires --oa-notice-file <path>"))?;
            let app = opts
                .application_file
                .as_deref()
                .ok_or_else(|| String::from("File mode for oa requires --application-file <path>"))?;
            if opts.prior_art_files.is_empty() {
                return Err(String::from(
                    "File mode for oa requires at least one --prior-art-file <path>",
                ));
            }
            let oa_notice_file_id = upload_file_for_cli(base_url, notice, "oa_notice", opts.timeout_sec)?;
            let application_file_id = upload_file_for_cli(base_url, app, "application", opts.timeout_sec)?;
            let mut prior_ids: Vec<Value> = Vec::new();
            for p in &opts.prior_art_files {
                let file_id = upload_file_for_cli(base_url, p, "prior_art", opts.timeout_sec)?;
                prior_ids.push(Value::String(file_id));
            }
            payload["oa_notice_file_id"] = Value::String(oa_notice_file_id);
            payload["application_file_id"] = Value::String(application_file_id);
            payload["prior_art_file_ids"] = Value::Array(prior_ids);
            if payload.get("oa_text").is_none() {
                payload["oa_text"] = Value::Null;
            }
        }
        "compare" => {
            let app = opts
                .application_file
                .as_deref()
                .ok_or_else(|| String::from("File mode for compare requires --application-file <path>"))?;
            if opts.prior_art_files.is_empty() {
                return Err(String::from(
                    "File mode for compare requires at least one --prior-art-file <path>",
                ));
            }
            let application_file_id = upload_file_for_cli(base_url, app, "application", opts.timeout_sec)?;
            let mut prior_ids: Vec<Value> = Vec::new();
            for p in &opts.prior_art_files {
                let file_id = upload_file_for_cli(base_url, p, "prior_art", opts.timeout_sec)?;
                prior_ids.push(Value::String(file_id));
            }
            payload["application_file_id"] = Value::String(application_file_id);
            payload["prior_art_file_ids"] = Value::Array(prior_ids);
        }
        "polish" => {
            let app = opts
                .application_file
                .as_deref()
                .ok_or_else(|| String::from("File mode for polish requires --application-file <path>"))?;
            let application_file_id = upload_file_for_cli(base_url, app, "application", opts.timeout_sec)?;
            payload["application_file_id"] = Value::String(application_file_id);
        }
        _ => return Err(format!("Unsupported workflow: {workflow}")),
    }

    Ok(payload)
}

fn wait_for_api_ready(base_url: &str, timeout_sec: u64) -> Result<(), String> {
    let deadline = Instant::now() + Duration::from_secs(timeout_sec.max(1));
    let health_url = format!("{base_url}/openapi.json");
    loop {
        if Instant::now() > deadline {
            return Err(String::from("Backend API did not become ready within timeout"));
        }
        match ureq::get(&health_url).call() {
            Ok(resp) if (200..300).contains(&resp.status()) => return Ok(()),
            _ => sleep(Duration::from_millis(250)),
        }
    }
}

fn post_json(base_url: &str, path: &str, body: &Value, timeout_sec: u64, llm: &LlmHeaders) -> Result<Value, String> {
    let url = format!("{base_url}{path}");
    let timeout = Duration::from_secs(timeout_sec.max(1));
    let agent = ureq::AgentBuilder::new()
        .timeout_connect(timeout)
        .timeout_read(timeout)
        .build();
    let mut req = agent.post(&url).set("Content-Type", "application/json");
    if let Some(v) = llm.provider.as_deref() {
        req = req.set("X-LLM-Provider", v);
    }
    if let Some(v) = llm.model.as_deref() {
        req = req.set("X-LLM-Model", v);
    }
    if let Some(v) = llm.vision_model.as_deref() {
        req = req.set("X-LLM-Vision-Model", v);
    }
    if let Some(v) = llm.base_url.as_deref() {
        req = req.set("X-LLM-Base-URL", v);
    }
    if let Some(v) = llm.api_key.as_deref() {
        req = req.set("X-LLM-API-Key", v);
    }
    if let Some(v) = llm.temperature.as_deref() {
        req = req.set("X-LLM-Temperature", v);
    }

    match req.send_string(&body.to_string()) {
        Ok(resp) => {
            let text = resp
                .into_string()
                .map_err(|e| format!("Failed to read API response body: {e}"))?;
            serde_json::from_str::<Value>(&text).map_err(|e| format!("Failed to parse API JSON response: {e}"))
        }
        Err(ureq::Error::Status(status, resp)) => {
            let body_text = resp.into_string().unwrap_or_default();
            Err(format!("API status={status}, body={body_text}"))
        }
        Err(e) => Err(format!("HTTP request failed: {e}")),
    }
}

fn maybe_continue_draft(base_url: &str, start_resp: &Value, timeout_sec: u64, llm: &LlmHeaders) -> Result<Value, String> {
    let status = start_resp
        .get("status")
        .and_then(Value::as_str)
        .unwrap_or_default();
    if status != "waiting_human" {
        return Ok(start_resp.clone());
    }
    let session_id = start_resp
        .get("session_id")
        .and_then(Value::as_str)
        .ok_or_else(|| String::from("draft/start returned waiting_human but missing session_id"))?;
    let claims = start_resp
        .get("data")
        .and_then(|v| v.get("claims"))
        .cloned()
        .ok_or_else(|| String::from("draft/start returned waiting_human but missing data.claims"))?;

    let continue_payload = json!({
        "session_id": session_id,
        "approved_claims": claims
    });
    post_json(base_url, "/api/v1/draft/continue", &continue_payload, timeout_sec, llm)
}

fn tail_log(path: &Path, max_lines: usize) -> String {
    let content = match fs::read_to_string(path) {
        Ok(v) => v,
        Err(_) => return String::new(),
    };
    let lines: Vec<&str> = content.lines().collect();
    let start = lines.len().saturating_sub(max_lines);
    lines[start..].join("\n")
}

fn execute_cli_task(opts: &CliOptions) -> Result<Value, String> {
    if opts.show_help {
        return Ok(json!({ "ok": true, "help": cli_help_text() }));
    }
    if opts.show_version {
        return Ok(json!({
            "ok": true,
            "product": "M-Cube",
            "version": env!("CARGO_PKG_VERSION")
        }));
    }

    let workflow = opts
        .workflow
        .as_deref()
        .ok_or_else(|| String::from("Missing required argument: --workflow"))?;
    let runtime_root = resolve_runtime_root_for_cli();
    let log_dir = runtime_root.join("logs");
    fs::create_dir_all(&log_dir).map_err(|e| format!("Failed to create CLI log directory: {e}"))?;
    let log_file = log_dir.join("backend-sidecar.log");

    append_log(
        &log_file,
        &format!("=== Launch M-Cube backend sidecar (CLI) at {:?} ===", std::time::SystemTime::now()),
    );
    kill_stale_sidecars_by_name("mcube-backend", &log_file);
    let mut runtime = spawn_sidecar(&runtime_root, &log_file)?;
    append_log(&log_file, "Backend sidecar spawned (CLI mode).");

    let llm = build_effective_llm_headers(opts);
    let result = (|| {
        let base_url = "http://127.0.0.1:8000";
        // Force local loopback calls to bypass any system proxy settings.
        std::env::set_var("NO_PROXY", "127.0.0.1,localhost");
        std::env::set_var("no_proxy", "127.0.0.1,localhost");
        wait_for_api_ready(base_url, opts.timeout_sec)?;
        let base_payload = if let Some(input_arg) = opts.input.as_deref() {
            read_input_json(input_arg)?
        } else {
            json!({})
        };
        validate_cli_input_schema(workflow, &base_payload)?;
        let input_json = build_cli_request_payload(opts, base_payload, base_url)?;
        let response = match workflow {
            "draft" => {
                let start_resp = post_json(base_url, "/api/v1/draft/start", &input_json, opts.timeout_sec, &llm)?;
                maybe_continue_draft(base_url, &start_resp, opts.timeout_sec, &llm)?
            }
            "oa" => post_json(base_url, "/api/v1/oa/start", &input_json, opts.timeout_sec, &llm)?,
            "compare" => post_json(base_url, "/api/v1/compare/start", &input_json, opts.timeout_sec, &llm)?,
            "polish" => post_json(base_url, "/api/v1/polish/start", &input_json, opts.timeout_sec, &llm)?,
            _ => return Err(format!("Unsupported workflow: {workflow}")),
        };
        Ok(response)
    })();

    if result.is_err() {
        let log_tail = tail_log(&runtime.log_file, 80);
        let detail = format!(
            "{}\nlog_file={}\nlog_tail=\n{}",
            result.clone().err().unwrap_or_default(),
            runtime.log_file.display(),
            log_tail
        );
        shutdown_sidecar(&mut runtime.child, &runtime.log_file);
        return Err(detail);
    }

    shutdown_sidecar(&mut runtime.child, &runtime.log_file);
    result
}

fn print_json_stdout(value: &Value, pretty: bool) {
    if pretty {
        println!(
            "{}",
            serde_json::to_string_pretty(value).unwrap_or_else(|_| value.to_string())
        );
    } else {
        println!("{value}");
    }
}

fn write_cli_output_file(value: &Value, pretty: bool, output_path: Option<&str>) -> Result<PathBuf, String> {
    let target = if let Some(path) = output_path {
        PathBuf::from(path)
    } else {
        PathBuf::from("mcube-cli-last-result.json")
    };
    let text = if pretty {
        serde_json::to_string_pretty(value).unwrap_or_else(|_| value.to_string())
    } else {
        value.to_string()
    };
    fs::write(&target, text).map_err(|e| format!("Failed to write CLI output file: {e}"))?;
    Ok(target)
}

fn run_cli_mode() -> i32 {
    let args: Vec<String> = std::env::args().skip(1).collect();
    let opts = match parse_cli_args(&args) {
        Ok(v) => v,
        Err(e) => {
            print_json_stdout(
                &json!({
                    "ok": false,
                    "error": { "code": "CLI_INVALID_ARGUMENT", "message": e },
                    "help": cli_help_text(),
                }),
                false,
            );
            return 2;
        }
    };

    match execute_cli_task(&opts) {
        Ok(payload) => {
            let out_json = json!({
                "ok": true,
                "workflow": opts.workflow,
                "result": payload
            });
            let _ = write_cli_output_file(&out_json, opts.pretty, opts.output.as_deref());
            print_json_stdout(&out_json, opts.pretty);
            0
        }
        Err(err) => {
            let out_json = json!({
                "ok": false,
                "error": { "code": "CLI_EXECUTION_FAILED", "message": err }
            });
            let _ = write_cli_output_file(&out_json, opts.pretty, opts.output.as_deref());
            print_json_stdout(&out_json, opts.pretty);
            3
        }
    }
}

fn run_gui_mode() {
    let app = tauri::Builder::default()
        .manage(BackendProcessState(Mutex::new(None)))
        .setup(|app| {
            set_main_window_icon(app);
            configure_main_window_platform(app);

            if cfg!(debug_assertions) {
                return Ok(());
            }

            let app_handle = app.handle().clone();
            let app_data_dir = app_handle
                .path()
                .app_data_dir()
                .map_err(|e| format!("Failed to resolve app data directory: {e}"))?;
            fs::create_dir_all(&app_data_dir).map_err(|e| format!("Failed to create app data directory: {e}"))?;
            let runtime_root = app_data_dir.join("runtime");
            let log_dir = runtime_root.join("logs");
            fs::create_dir_all(&log_dir).map_err(|e| format!("Failed to create log directory: {e}"))?;
            let log_file = log_dir.join("backend-sidecar.log");

            append_log(
                &log_file,
                &format!("=== Launch M-Cube backend sidecar at {:?} ===", std::time::SystemTime::now()),
            );
            kill_stale_sidecars_by_name("mcube-backend", &log_file);

            match spawn_sidecar(&runtime_root, &log_file) {
                Ok(runtime) => {
                    let state = app_handle.state::<BackendProcessState>();
                    let mut guard = state
                        .0
                        .lock()
                        .map_err(|_| String::from("Failed to lock backend process state"))?;
                    *guard = Some(runtime.child);
                    append_log(&log_file, "Backend sidecar spawned.");
                }
                Err(e) => {
                    append_log(&log_file, &e);
                }
            }
            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("error while building tauri application");

    app.run(|app_handle, event| {
        if matches!(event, RunEvent::Exit | RunEvent::ExitRequested { .. }) {
            let log_file = resolve_log_file(&app_handle);
            let state = app_handle.state::<BackendProcessState>();
            let child_to_kill = match state.0.lock() {
                Ok(mut guard) => guard.take(),
                Err(_) => None,
            };
            if let Some(mut child) = child_to_kill {
                shutdown_sidecar(&mut child, &log_file);
            }
        }
    });
}

fn main() {
    let is_cli = std::env::args().any(|arg| arg == "--cli");
    if is_cli {
        let code = run_cli_mode();
        std::process::exit(code);
    }
    run_gui_mode();
}

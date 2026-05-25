use axum::body::Body;
use axum::extract::{DefaultBodyLimit, Multipart, Path as AxumPath, State};
use axum::http::{header, HeaderValue, StatusCode};
use axum::response::{Html, IntoResponse, Response};
use axum::routing::{delete, get, post, put};
use axum::{Json, Router};
use chrono::Local;
use regex::Regex;
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use std::env;
use std::ffi::OsStr;
use std::fs::{self, File};
use std::io::{Read, Write};
use std::net::SocketAddr;
use std::path::{Component, Path, PathBuf};
use std::process::Command;
use std::sync::Arc;
use tower_http::compression::CompressionLayer;
use tower_http::limit::RequestBodyLimitLayer;
use tower_http::services::ServeDir;
use tower_http::trace::TraceLayer;
use tracing::{info, warn};
use tracing_subscriber::{layer::SubscriberExt, util::SubscriberInitExt, EnvFilter};
use uuid::Uuid;
use walkdir::WalkDir;
use zip::ZipArchive;

const DEFAULT_TEMPLATE_ID: &str = "builtin-default";
const DEFAULT_BASE_URL: &str = "https://api.chshapi.org/v1";
const DEFAULT_MODEL: &str = "gpt-5.5";
const MAX_FOLDER_UPLOAD_FILES: usize = 1200;
const MAX_FOLDER_UPLOAD_BYTES: u64 = 500 * 1024 * 1024;
const MAX_SINGLE_UPLOAD_BYTES: usize = 500 * 1024 * 1024;
const MAX_UPLOAD_REQUEST_BYTES: usize = 550 * 1024 * 1024;
const MAX_TEMPLATE_BYTES: usize = 10 * 1024 * 1024;
const MAX_ZIP_ENTRIES: usize = 2000;
const MAX_UNPACKED_BYTES: u64 = 500 * 1024 * 1024;

#[derive(Clone)]
struct AppState {
    app_root: PathBuf,
    data_root: PathBuf,
    projects_root: PathBuf,
    settings_root: PathBuf,
    templates_root: PathBuf,
    static_dir: PathBuf,
}

#[derive(Debug)]
struct ApiError {
    status: StatusCode,
    detail: String,
}

impl ApiError {
    fn bad_request(detail: impl Into<String>) -> Self {
        Self {
            status: StatusCode::BAD_REQUEST,
            detail: detail.into(),
        }
    }

    fn not_found(detail: impl Into<String>) -> Self {
        Self {
            status: StatusCode::NOT_FOUND,
            detail: detail.into(),
        }
    }

    fn internal(detail: impl Into<String>) -> Self {
        Self {
            status: StatusCode::INTERNAL_SERVER_ERROR,
            detail: detail.into(),
        }
    }
}

impl IntoResponse for ApiError {
    fn into_response(self) -> Response {
        (self.status, Json(json!({ "detail": self.detail }))).into_response()
    }
}

type ApiResult<T> = Result<T, ApiError>;

#[derive(Deserialize)]
struct LlmSettingsPayload {
    api_key: Option<String>,
    base_url: Option<String>,
    model: Option<String>,
}

#[derive(Deserialize)]
struct PaperOptionsPayload {
    template_id: Option<String>,
    target_body_pages: Option<u64>,
}

#[derive(Deserialize, Serialize)]
struct ModelAssistantPayload {
    problem_ref: String,
    model_name: String,
    user_goal: Option<String>,
}

#[derive(Deserialize, Serialize)]
struct ProblemSelectionPayload {
    problem_id: String,
}

#[tokio::main]
async fn main() -> anyhow::Result<()> {
    init_tracing();
    let state = Arc::new(AppState::discover()?);
    state.ensure_dirs()?;

    let port = env::var("MODELING_WORKBENCH_PORT")
        .ok()
        .and_then(|value| value.parse::<u16>().ok())
        .unwrap_or(8765);
    let addr = SocketAddr::from(([127, 0, 0, 1], port));
    let app = build_router(state);

    info!("Rust Math Modeling Workbench listening on http://{addr}");
    let listener = tokio::net::TcpListener::bind(addr).await?;
    axum::serve(listener, app).await?;
    Ok(())
}

fn init_tracing() {
    let filter = EnvFilter::try_from_default_env()
        .unwrap_or_else(|_| EnvFilter::new("modeling_workbench_server=info,tower_http=info"));
    if tracing_subscriber::registry()
        .with(filter)
        .with(tracing_subscriber::fmt::layer().compact())
        .try_init()
        .is_err()
    {
        warn!("tracing subscriber already initialized");
    }
}

fn build_router(state: Arc<AppState>) -> Router {
    Router::new()
        .route("/", get(index))
        .route("/api/health", get(health))
        .route("/api/environments", get(environments))
        .route("/api/skills/backend", get(backend_skills))
        .route("/api/settings/llm", get(read_llm_settings))
        .route("/api/settings/llm", put(update_llm_settings))
        .route("/api/settings/llm", delete(delete_llm_settings))
        .route("/api/templates", get(read_templates))
        .route("/api/templates", post(upload_template))
        .route("/api/templates/:template_id", delete(remove_template))
        .route("/api/projects", get(projects))
        .route("/api/projects", post(create_project_from_upload))
        .route("/api/projects/folder", post(create_project_from_folder))
        .route("/api/projects/:project_id", get(project_detail_handler))
        .route(
            "/api/projects/:project_id/skills/report",
            post(write_project_backend_skill_report_handler),
        )
        .route(
            "/api/projects/:project_id/paper/options",
            put(update_paper_options),
        )
        .route(
            "/api/projects/:project_id/problem/selection",
            put(select_project_problem),
        )
        .route("/api/projects/:project_id/compile", post(compile_project))
        .route(
            "/api/projects/:project_id/model/generate",
            post(generate_model),
        )
        .route("/api/projects/:project_id/model/run", post(run_model))
        .route(
            "/api/projects/:project_id/specialized/generate",
            post(generate_specialized),
        )
        .route(
            "/api/projects/:project_id/specialized/run",
            post(run_specialized),
        )
        .route("/api/projects/:project_id/paper/fill", post(fill_paper))
        .route(
            "/api/projects/:project_id/computed/run",
            post(run_computed_solution),
        )
        .route(
            "/api/projects/:project_id/paper/review",
            post(review_paper_handler),
        )
        .route(
            "/api/projects/:project_id/auto/run",
            post(run_auto_workflow_handler),
        )
        .route(
            "/api/projects/:project_id/progress",
            get(project_progress_handler),
        )
        .route(
            "/api/projects/:project_id/llm/analyze",
            post(run_llm_analysis),
        )
        .route(
            "/api/projects/:project_id/llm/model-assistant",
            post(run_model_assistant),
        )
        .route(
            "/api/projects/:project_id/download/*relative_path",
            get(download_artifact),
        )
        .nest_service("/static", ServeDir::new(state.static_dir.clone()))
        .layer(CompressionLayer::new())
        .layer(DefaultBodyLimit::disable())
        .layer(RequestBodyLimitLayer::new(MAX_UPLOAD_REQUEST_BYTES))
        .layer(TraceLayer::new_for_http())
        .with_state(state)
}

impl AppState {
    fn discover() -> anyhow::Result<Self> {
        let current = env::current_dir()?;
        let app_root = env::var("MODELING_WORKBENCH_APP_ROOT")
            .map(PathBuf::from)
            .unwrap_or_else(|_| {
                if current.join("app").join("static").exists() {
                    current.clone()
                } else {
                    current
                        .parent()
                        .map(Path::to_path_buf)
                        .unwrap_or(current.clone())
                }
            });
        let data_root = env::var("MODELING_WORKBENCH_DATA_ROOT")
            .map(PathBuf::from)
            .unwrap_or_else(|_| app_root.join("data"));
        Ok(Self {
            static_dir: app_root.join("app").join("static"),
            projects_root: data_root.join("projects"),
            settings_root: data_root.join("settings"),
            templates_root: data_root.join("settings").join("templates"),
            app_root,
            data_root,
        })
    }

    fn ensure_dirs(&self) -> anyhow::Result<()> {
        fs::create_dir_all(&self.projects_root)?;
        fs::create_dir_all(&self.settings_root)?;
        fs::create_dir_all(&self.templates_root)?;
        Ok(())
    }

    fn project_root(&self, project_id: &str) -> ApiResult<PathBuf> {
        let pattern = format!("{project_id}-");
        let mut matches = Vec::new();
        for entry in fs::read_dir(&self.projects_root).map_err(io_error)? {
            let entry = entry.map_err(io_error)?;
            if entry.file_type().map_err(io_error)?.is_dir()
                && entry.file_name().to_string_lossy().starts_with(&pattern)
            {
                matches.push(entry.path());
            }
        }
        matches.sort();
        matches
            .into_iter()
            .next()
            .ok_or_else(|| ApiError::not_found("项目不存在"))
    }
}

async fn index(State(state): State<Arc<AppState>>) -> ApiResult<Html<String>> {
    let html = tokio::fs::read_to_string(state.static_dir.join("index.html"))
        .await
        .map_err(io_error)?;
    Ok(Html(html))
}

async fn health() -> Json<Value> {
    Json(json!({
        "status": "ok",
        "backend": "rust",
        "version": env!("CARGO_PKG_VERSION")
    }))
}

async fn environments() -> Json<Value> {
    let python = detect_command(&["python", "--version"], None);
    Json(json!({
        "local_python": {
            "available": python["available"].as_bool().unwrap_or(false),
            "executable": which("python").unwrap_or_default(),
            "version": python["detail"].as_str().unwrap_or("").replace("Python ", "")
        },
        "rust": {
            "available": true,
            "detail": env!("CARGO_PKG_VERSION")
        },
        "docker": detect_command(&["docker", "--version"], Some(&["docker", "info"])),
        "wsl": detect_command(&["wsl", "--version"], None)
    }))
}

async fn backend_skills(State(state): State<Arc<AppState>>) -> ApiResult<Json<Value>> {
    let code = r#"
import json
from app.services.backend_skills import (
    list_backend_skills,
    list_model_method_routes,
    list_model_selection_rubric,
    list_standard_paper_checklist,
    list_standard_paper_workflow,
)
print(json.dumps({
    "skills": list_backend_skills(),
    "standard_paper_workflow": list_standard_paper_workflow(),
    "standard_paper_checklist": list_standard_paper_checklist(),
    "model_method_routes": list_model_method_routes(),
    "model_selection_rubric": list_model_selection_rubric(),
}, ensure_ascii=False))
"#;
    let value = run_python_code(&state, code, None, "", None)?;
    Ok(Json(value))
}

async fn read_llm_settings(State(state): State<Arc<AppState>>) -> Json<Value> {
    Json(get_llm_settings(&state))
}

async fn update_llm_settings(
    State(state): State<Arc<AppState>>,
    Json(payload): Json<LlmSettingsPayload>,
) -> ApiResult<Json<Value>> {
    let mut current = load_json_optional(&state.settings_root.join("llm.json"))?
        .and_then(|value| value.as_object().cloned())
        .unwrap_or_default();
    if let Some(api_key) = normalize_api_key(payload.api_key)? {
        current.insert("api_key".to_string(), Value::String(api_key));
    }
    if let Some(base_url) = normalize_base_url(payload.base_url)? {
        current.insert("base_url".to_string(), Value::String(base_url));
    }
    if let Some(model) = normalize_model(payload.model)? {
        current.insert("model".to_string(), Value::String(model));
    }
    save_json(
        &state.settings_root.join("llm.json"),
        &Value::Object(current),
    )?;
    Ok(Json(get_llm_settings(&state)))
}

async fn delete_llm_settings(State(state): State<Arc<AppState>>) -> ApiResult<Json<Value>> {
    let path = state.settings_root.join("llm.json");
    if path.exists() {
        fs::remove_file(path).map_err(io_error)?;
    }
    Ok(Json(get_llm_settings(&state)))
}

async fn read_templates(State(state): State<Arc<AppState>>) -> ApiResult<Json<Value>> {
    Ok(Json(json!({ "templates": list_templates(&state)? })))
}

async fn upload_template(
    State(state): State<Arc<AppState>>,
    mut multipart: Multipart,
) -> ApiResult<Json<Value>> {
    let mut name: Option<String> = None;
    let mut filename = String::new();
    let mut content = Vec::new();
    while let Some(field) = multipart.next_field().await.map_err(multipart_error)? {
        let field_name = field.name().unwrap_or("").to_string();
        if field_name == "name" {
            name = Some(field.text().await.map_err(multipart_error)?);
        } else if field_name == "file" {
            filename = field.file_name().unwrap_or("template").to_string();
            content = field.bytes().await.map_err(multipart_error)?.to_vec();
        }
    }
    let template = create_template_record(&state, name, &filename, content)?;
    Ok(Json(
        json!({ "template": template, "templates": list_templates(&state)? }),
    ))
}

async fn remove_template(
    State(state): State<Arc<AppState>>,
    AxumPath(template_id): AxumPath<String>,
) -> ApiResult<Json<Value>> {
    if template_id == DEFAULT_TEMPLATE_ID {
        return Err(ApiError::bad_request("内置模板不能删除"));
    }
    let index_path = state.templates_root.join("index.json");
    let mut index = load_json_optional(&index_path)?
        .and_then(|value| value.as_array().cloned())
        .unwrap_or_default();
    let before = index.len();
    index.retain(|item| item.get("id").and_then(Value::as_str) != Some(template_id.as_str()));
    if before == index.len() {
        return Err(ApiError::not_found("模板不存在"));
    }
    for entry in fs::read_dir(&state.templates_root).map_err(io_error)? {
        let entry = entry.map_err(io_error)?;
        if entry
            .file_name()
            .to_string_lossy()
            .starts_with(&format!("{template_id}."))
        {
            let _ = fs::remove_file(entry.path());
        }
    }
    save_json(&index_path, &Value::Array(index))?;
    Ok(Json(
        json!({ "deleted": template_id, "templates": list_templates(&state)? }),
    ))
}

async fn projects(State(state): State<Arc<AppState>>) -> ApiResult<Json<Value>> {
    Ok(Json(Value::Array(list_projects(&state)?)))
}

async fn create_project_from_upload(
    State(state): State<Arc<AppState>>,
    mut multipart: Multipart,
) -> ApiResult<Json<Value>> {
    let mut filename = String::new();
    let mut content = Vec::new();
    while let Some(field) = multipart.next_field().await.map_err(multipart_error)? {
        if field.name() == Some("file") {
            filename = field.file_name().unwrap_or("upload").to_string();
            content = field.bytes().await.map_err(multipart_error)?.to_vec();
        }
    }
    if filename.is_empty() || content.is_empty() {
        return Err(ApiError::bad_request("缺少上传文件"));
    }
    if content.len() > MAX_SINGLE_UPLOAD_BYTES {
        return Err(ApiError::bad_request("上传文件过大，请控制在 500 MB 内"));
    }
    let meta = create_project_dirs(&state, &filename)?;
    let root = PathBuf::from(meta.get("root").and_then(Value::as_str).unwrap_or_default());
    let upload_path = root.join("uploads").join(file_name_only(&filename));
    fs::write(&upload_path, content).map_err(io_error)?;
    unpack_or_copy(&upload_path, &root.join("raw"))?;
    analyze_project_with_python(
        &state,
        &root,
        meta.get("id").and_then(Value::as_str).unwrap_or(""),
    )?;
    project_detail(&state, meta.get("id").and_then(Value::as_str).unwrap_or(""))
}

async fn create_project_from_folder(
    State(state): State<Arc<AppState>>,
    mut multipart: Multipart,
) -> ApiResult<Json<Value>> {
    let mut folder_name = "赛题文件夹".to_string();
    let mut files = Vec::new();
    let mut total_bytes: u64 = 0;
    while let Some(field) = multipart.next_field().await.map_err(multipart_error)? {
        if field.name() == Some("folder_name") {
            folder_name = field.text().await.map_err(multipart_error)?;
            continue;
        }
        if field.name() == Some("files") {
            if files.len() >= MAX_FOLDER_UPLOAD_FILES {
                return Err(ApiError::bad_request("文件夹中文件过多"));
            }
            let filename = field.file_name().unwrap_or("file").to_string();
            let bytes = field.bytes().await.map_err(multipart_error)?.to_vec();
            total_bytes += bytes.len() as u64;
            if total_bytes > MAX_FOLDER_UPLOAD_BYTES {
                return Err(ApiError::bad_request(
                    "文件夹总大小过大，请控制在 500 MB 内",
                ));
            }
            files.push((filename, bytes));
        }
    }
    if files.is_empty() {
        return Err(ApiError::bad_request("请选择一个包含赛题材料的文件夹"));
    }
    let mut meta = create_project_dirs(&state, &folder_name)?;
    let root = PathBuf::from(meta.get("root").and_then(Value::as_str).unwrap_or_default());
    let raw_dir = root.join("raw");
    let mut manifest = Vec::new();
    for (filename, bytes) in files {
        let rel = safe_relative_path(&filename)?;
        let target = raw_dir.join(&rel);
        fs::create_dir_all(target.parent().unwrap_or(&raw_dir)).map_err(io_error)?;
        fs::write(&target, &bytes).map_err(io_error)?;
        manifest.push(json!({
            "path": normalize_slashes(&rel),
            "size": bytes.len(),
            "content_type": ""
        }));
    }
    save_json(
        &root.join("uploads").join("folder_upload_manifest.json"),
        &Value::Array(manifest),
    )?;
    if let Some(obj) = meta.as_object_mut() {
        obj.insert(
            "folder_upload".to_string(),
            json!({"file_count": files_len_from_raw(&raw_dir), "total_bytes": total_bytes}),
        );
        save_json(&root.join("metadata.json"), &meta)?;
    }
    analyze_project_with_python(
        &state,
        &root,
        meta.get("id").and_then(Value::as_str).unwrap_or(""),
    )?;
    project_detail(&state, meta.get("id").and_then(Value::as_str).unwrap_or(""))
}

async fn project_detail_handler(
    State(state): State<Arc<AppState>>,
    AxumPath(project_id): AxumPath<String>,
) -> ApiResult<Json<Value>> {
    project_detail(&state, &project_id)
}

async fn write_project_backend_skill_report_handler(
    State(state): State<Arc<AppState>>,
    AxumPath(project_id): AxumPath<String>,
) -> ApiResult<Json<Value>> {
    python_endpoint(
        &state,
        &project_id,
        "write_project_backend_skill_report",
        None,
    )
}

async fn update_paper_options(
    State(state): State<Arc<AppState>>,
    AxumPath(project_id): AxumPath<String>,
    Json(payload): Json<PaperOptionsPayload>,
) -> ApiResult<Json<Value>> {
    let root = state.project_root(&project_id)?;
    let mut meta = load_json(&root.join("metadata.json"))?;
    let template_id = payload
        .template_id
        .unwrap_or_else(|| DEFAULT_TEMPLATE_ID.to_string());
    validate_template_id(&state, &template_id)?;
    if let Some(target_pages) = payload.target_body_pages {
        if !(1..=100).contains(&target_pages) {
            return Err(ApiError::bad_request("正文目标页数需在 1 到 100 之间"));
        }
    }
    meta.as_object_mut()
        .ok_or_else(|| ApiError::internal("metadata.json 格式错误"))?
        .insert(
            "paper_options".to_string(),
            json!({"template_id": template_id, "target_body_pages": payload.target_body_pages}),
        );
    save_json(&root.join("metadata.json"), &meta)?;
    Ok(Json(json!({
        "paper_options": meta.get("paper_options").cloned().unwrap_or(Value::Null),
        "project": project_detail_value(&state, &project_id)?
    })))
}

async fn select_project_problem(
    State(state): State<Arc<AppState>>,
    AxumPath(project_id): AxumPath<String>,
    Json(payload): Json<ProblemSelectionPayload>,
) -> ApiResult<Json<Value>> {
    python_endpoint(
        &state,
        &project_id,
        "select_project_problem",
        Some(json!(payload)),
    )
}

async fn compile_project(
    State(state): State<Arc<AppState>>,
    AxumPath(project_id): AxumPath<String>,
) -> ApiResult<Json<Value>> {
    python_endpoint(&state, &project_id, "compile_project", None)
}

async fn generate_model(
    State(state): State<Arc<AppState>>,
    AxumPath(project_id): AxumPath<String>,
) -> ApiResult<Json<Value>> {
    python_endpoint(&state, &project_id, "generate_model", None)
}

async fn run_model(
    State(state): State<Arc<AppState>>,
    AxumPath(project_id): AxumPath<String>,
) -> ApiResult<Json<Value>> {
    python_endpoint(&state, &project_id, "run_model", None)
}

async fn generate_specialized(
    State(state): State<Arc<AppState>>,
    AxumPath(project_id): AxumPath<String>,
) -> ApiResult<Json<Value>> {
    python_endpoint(&state, &project_id, "generate_specialized", None)
}

async fn run_specialized(
    State(state): State<Arc<AppState>>,
    AxumPath(project_id): AxumPath<String>,
) -> ApiResult<Json<Value>> {
    python_endpoint(&state, &project_id, "run_specialized", None)
}

async fn fill_paper(
    State(state): State<Arc<AppState>>,
    AxumPath(project_id): AxumPath<String>,
) -> ApiResult<Json<Value>> {
    python_endpoint(&state, &project_id, "fill_paper", None)
}

async fn run_computed_solution(
    State(state): State<Arc<AppState>>,
    AxumPath(project_id): AxumPath<String>,
) -> ApiResult<Json<Value>> {
    python_endpoint(&state, &project_id, "run_project_computed_solution", None)
}

async fn review_paper_handler(
    State(state): State<Arc<AppState>>,
    AxumPath(project_id): AxumPath<String>,
) -> ApiResult<Json<Value>> {
    python_endpoint(&state, &project_id, "review_project_paper", None)
}

async fn run_auto_workflow_handler(
    State(state): State<Arc<AppState>>,
    AxumPath(project_id): AxumPath<String>,
) -> ApiResult<Json<Value>> {
    python_endpoint(&state, &project_id, "run_project_auto_workflow", None)
}

async fn project_progress_handler(
    State(state): State<Arc<AppState>>,
    AxumPath(project_id): AxumPath<String>,
) -> ApiResult<Json<Value>> {
    let root = state.project_root(&project_id)?;
    let meta = load_json(&root.join("metadata.json"))?;
    let progress_path = root.join("artifacts").join("auto_workflow_progress.json");
    let progress = if progress_path.exists() {
        load_json(&progress_path)?
    } else {
        meta.get("auto_workflow_progress").cloned().unwrap_or_else(|| json!({}))
    };
    Ok(Json(json!({
        "project_id": project_id,
        "status": meta.get("auto_workflow_status").and_then(Value::as_str).unwrap_or("idle"),
        "progress": progress,
        "artifacts": meta.get("artifacts").cloned().unwrap_or_else(|| json!({})),
        "error": meta.get("auto_workflow_error").and_then(Value::as_str).unwrap_or("")
    })))
}

async fn run_llm_analysis(
    State(state): State<Arc<AppState>>,
    AxumPath(project_id): AxumPath<String>,
) -> ApiResult<Json<Value>> {
    python_endpoint(&state, &project_id, "run_project_llm_analysis", None)
}

async fn run_model_assistant(
    State(state): State<Arc<AppState>>,
    AxumPath(project_id): AxumPath<String>,
    Json(payload): Json<ModelAssistantPayload>,
) -> ApiResult<Json<Value>> {
    if payload.problem_ref.trim().is_empty() {
        return Err(ApiError::bad_request("请指定要辅助求解的问题"));
    }
    if payload.model_name.trim().is_empty() {
        return Err(ApiError::bad_request("请填写模型或算法名称"));
    }
    python_endpoint(
        &state,
        &project_id,
        "run_project_model_assistant",
        Some(serde_json::to_value(payload).map_err(|err| ApiError::internal(err.to_string()))?),
    )
}

async fn download_artifact(
    State(state): State<Arc<AppState>>,
    AxumPath((project_id, relative_path)): AxumPath<(String, String)>,
) -> ApiResult<Response> {
    let root = state.project_root(&project_id)?;
    let target = if relative_path == "support.zip" {
        make_support_zip(&root)?
    } else {
        let rel = safe_relative_path(&relative_path)?;
        let target = root.join(rel);
        ensure_inside(&root, &target)?;
        target
    };
    if !target.is_file() {
        return Err(ApiError::not_found("文件不存在"));
    }
    let bytes = tokio::fs::read(&target).await.map_err(io_error)?;
    let mime = mime_guess::from_path(&target).first_or_octet_stream();
    let file_name = target
        .file_name()
        .and_then(OsStr::to_str)
        .unwrap_or("download")
        .to_string();
    let mut response = Response::new(Body::from(bytes));
    response.headers_mut().insert(
        header::CONTENT_TYPE,
        HeaderValue::from_str(mime.as_ref())
            .unwrap_or(HeaderValue::from_static("application/octet-stream")),
    );
    response.headers_mut().insert(
        header::CONTENT_DISPOSITION,
        HeaderValue::from_str(&content_disposition(&file_name))
            .unwrap_or(HeaderValue::from_static("attachment")),
    );
    response.headers_mut().insert(
        header::HeaderName::from_static("x-content-type-options"),
        HeaderValue::from_static("nosniff"),
    );
    Ok(response)
}

fn project_detail(state: &AppState, project_id: &str) -> ApiResult<Json<Value>> {
    Ok(Json(project_detail_value(state, project_id)?))
}

fn project_detail_value(state: &AppState, project_id: &str) -> ApiResult<Value> {
    let root = state.project_root(project_id)?;
    let mut meta = load_json(&root.join("metadata.json"))?;
    if let Some(obj) = meta.as_object_mut() {
        obj.remove("root");
    }
    let analysis_path = root.join("artifacts").join("analysis.json");
    let analysis = if analysis_path.exists() {
        load_json(&analysis_path)?
    } else {
        Value::Null
    };
    Ok(json!({ "metadata": meta, "analysis": analysis }))
}

fn list_projects(state: &AppState) -> ApiResult<Vec<Value>> {
    let mut projects = Vec::new();
    if !state.projects_root.exists() {
        return Ok(projects);
    }
    let mut roots = fs::read_dir(&state.projects_root)
        .map_err(io_error)?
        .filter_map(Result::ok)
        .filter(|entry| entry.file_type().map(|ft| ft.is_dir()).unwrap_or(false))
        .map(|entry| entry.path())
        .collect::<Vec<_>>();
    roots.sort();
    roots.reverse();
    for root in roots {
        let meta_path = root.join("metadata.json");
        if !meta_path.exists() {
            continue;
        }
        let Ok(mut meta) = load_json(&meta_path) else {
            continue;
        };
        if let Some(obj) = meta.as_object_mut() {
            if root.join("artifacts").join("analysis.json").exists() {
                obj.insert("analysis_available".to_string(), Value::Bool(true));
            }
        }
        projects.push(meta);
    }
    Ok(projects)
}

fn create_project_dirs(state: &AppState, original_name: &str) -> ApiResult<Value> {
    let project_id = format!(
        "{}-{}",
        Local::now().format("%Y%m%d-%H%M%S"),
        &Uuid::new_v4().simple().to_string()[..8]
    );
    let name = slugify(
        Path::new(original_name)
            .file_stem()
            .and_then(OsStr::to_str)
            .unwrap_or(original_name),
    );
    let root = state.projects_root.join(format!("{project_id}-{name}"));
    for child in ["uploads", "raw", "artifacts", "paper", "code", "results"] {
        fs::create_dir_all(root.join(child)).map_err(io_error)?;
    }
    let metadata = json!({
        "id": project_id,
        "name": name,
        "original_name": original_name,
        "created_at": Local::now().format("%Y-%m-%dT%H:%M:%S").to_string(),
        "root": root,
        "status": "created",
        "paper_options": {
            "template_id": DEFAULT_TEMPLATE_ID,
            "target_body_pages": null
        }
    });
    save_json(&root.join("metadata.json"), &metadata)?;
    Ok(metadata)
}

fn analyze_project_with_python(state: &AppState, root: &Path, project_id: &str) -> ApiResult<()> {
    let code = r#"
import json, os
from pathlib import Path
from app.services.store import load_json, save_json
from app.main import analyze_project_materials
root = Path(os.environ["BRIDGE_PROJECT_ROOT"])
meta = load_json(root / "metadata.json")
analyze_project_materials(root, meta)
print(json.dumps({"ok": True}, ensure_ascii=False))
"#;
    run_python_code(state, code, Some(root), project_id, None).map(|_| ())
}

fn python_endpoint(
    state: &AppState,
    project_id: &str,
    function_name: &str,
    payload: Option<Value>,
) -> ApiResult<Json<Value>> {
    let root = state.project_root(project_id)?;
    let code = if function_name == "run_project_model_assistant" {
        r#"
import json, os
from app.main import ModelAssistantPayload, run_project_model_assistant
payload = json.loads(os.environ.get("BRIDGE_PAYLOAD", "{}"))
result = run_project_model_assistant(os.environ["BRIDGE_PROJECT_ID"], ModelAssistantPayload(**payload))
print(json.dumps(result, ensure_ascii=False))
"#
        .to_string()
    } else if function_name == "select_project_problem" {
        r#"
import json, os
from app.main import ProblemSelectionPayload, select_project_problem
payload = json.loads(os.environ.get("BRIDGE_PAYLOAD", "{}"))
result = select_project_problem(os.environ["BRIDGE_PROJECT_ID"], ProblemSelectionPayload(**payload))
print(json.dumps(result, ensure_ascii=False))
"#
        .to_string()
    } else {
        format!(
            r#"
import json, os
from app.main import {function_name}
result = {function_name}(os.environ["BRIDGE_PROJECT_ID"])
print(json.dumps(result, ensure_ascii=False))
"#
        )
    };
    let value = run_python_code(state, &code, Some(&root), project_id, payload)?;
    Ok(Json(value))
}

fn run_python_code(
    state: &AppState,
    code: &str,
    project_root: Option<&Path>,
    project_id: &str,
    payload: Option<Value>,
) -> ApiResult<Value> {
    let mut command = Command::new("python");
    command
        .arg("-X")
        .arg("utf8")
        .arg("-c")
        .arg(code)
        .current_dir(&state.app_root)
        .env("MODELING_WORKBENCH_APP_ROOT", &state.app_root)
        .env("MODELING_WORKBENCH_DATA_ROOT", &state.data_root)
        .env("BRIDGE_PROJECT_ID", project_id);
    if let Some(root) = project_root {
        command.env("BRIDGE_PROJECT_ROOT", root);
    }
    if let Some(payload) = payload {
        command.env("BRIDGE_PAYLOAD", payload.to_string());
    }
    let output = command
        .output()
        .map_err(|err| ApiError::internal(format!("无法启动 Python 桥接进程：{err}")))?;
    if !output.status.success() {
        return Err(ApiError::internal(format!(
            "Python 桥接失败：{}",
            String::from_utf8_lossy(&output.stderr)
        )));
    }
    let stdout = String::from_utf8_lossy(&output.stdout);
    let json_line = stdout
        .lines()
        .rev()
        .find(|line| line.trim_start().starts_with('{') || line.trim_start().starts_with('['))
        .ok_or_else(|| ApiError::internal("Python 桥接未返回 JSON"))?;
    serde_json::from_str(json_line).map_err(|err| {
        ApiError::internal(format!("Python 桥接 JSON 解析失败：{err}; stdout={stdout}"))
    })
}

fn get_llm_settings(state: &AppState) -> Value {
    let stored = load_json_optional(&state.settings_root.join("llm.json"))
        .ok()
        .flatten()
        .and_then(|value| value.as_object().cloned())
        .unwrap_or_default();
    let env_key = env::var("OPENAI_API_KEY").unwrap_or_default();
    let api_key = stored
        .get("api_key")
        .and_then(Value::as_str)
        .unwrap_or(&env_key);
    let source = if stored
        .get("api_key")
        .and_then(Value::as_str)
        .unwrap_or("")
        .is_empty()
    {
        if env_key.is_empty() {
            ""
        } else {
            "env"
        }
    } else {
        "local"
    };
    json!({
        "provider": "openai",
        "configured": !api_key.is_empty(),
        "source": source,
        "masked_api_key": mask_api_key(api_key),
        "base_url": stored.get("base_url").and_then(Value::as_str).unwrap_or(DEFAULT_BASE_URL),
        "model": stored.get("model").and_then(Value::as_str).unwrap_or(DEFAULT_MODEL)
    })
}

fn list_templates(state: &AppState) -> ApiResult<Vec<Value>> {
    let mut templates = vec![json!({
        "id": DEFAULT_TEMPLATE_ID,
        "name": "内置 LaTeX 模板",
        "filename": "",
        "suffix": "",
        "mode": "builtin",
        "kind": "latex",
        "is_builtin": true,
        "created_at": "",
        "placeholders": [],
        "rule_summary": "",
        "extracted_chars": 0
    })];
    let index_path = state.templates_root.join("index.json");
    if let Some(Value::Array(items)) = load_json_optional(&index_path)? {
        templates.extend(items);
    }
    Ok(templates)
}

fn create_template_record(
    state: &AppState,
    name: Option<String>,
    filename: &str,
    content: Vec<u8>,
) -> ApiResult<Value> {
    if filename.is_empty() {
        return Err(ApiError::bad_request("缺少模板文件名"));
    }
    if content.is_empty() {
        return Err(ApiError::bad_request("模板文件为空"));
    }
    if content.len() > MAX_TEMPLATE_BYTES {
        return Err(ApiError::bad_request("模板文件过大，请控制在 10 MB 以内"));
    }
    let suffix = Path::new(filename)
        .extension()
        .and_then(OsStr::to_str)
        .map(|s| format!(".{}", s.to_lowercase()))
        .unwrap_or_default();
    let supported = [".tex", ".docx", ".pdf", ".txt", ".md"];
    if !supported.contains(&suffix.as_str()) {
        return Err(ApiError::bad_request(
            "当前支持 .tex/.docx/.pdf/.txt/.md 模板或格式说明",
        ));
    }
    let display_name = name
        .as_deref()
        .map(str::trim)
        .filter(|s| !s.is_empty())
        .unwrap_or_else(|| {
            Path::new(filename)
                .file_stem()
                .and_then(OsStr::to_str)
                .unwrap_or("template")
        });
    let template_id = format!(
        "{}-{}",
        slugify(display_name),
        &Uuid::new_v4().simple().to_string()[..8]
    );
    let path = state.templates_root.join(format!("{template_id}{suffix}"));
    fs::write(&path, &content).map_err(io_error)?;

    let (mode, kind, placeholders, rule_summary, extracted_chars) = if suffix == ".tex" {
        let text = String::from_utf8_lossy(&content).to_string();
        let placeholders = find_placeholders(&text);
        if !placeholders.iter().any(|item| item == "__BODY__")
            && ![
                "__BODY_START__",
                "__APPENDIX_START__",
                "__RESTATEMENT__",
                "__PROBLEM_ANALYSIS__",
                "__SOLVING__",
                "__VALIDATION__",
                "__APPENDIX__",
            ]
            .iter()
            .all(|required| placeholders.iter().any(|item| item == required))
        {
            return Err(ApiError::bad_request(
                "模板缺少可回填占位符，请提供 __BODY__ 或完整细粒度占位符",
            ));
        }
        (
            "body",
            "latex",
            placeholders,
            String::new(),
            text.chars().count(),
        )
    } else {
        let summary = if suffix == ".txt" || suffix == ".md" {
            String::from_utf8_lossy(&content)
                .chars()
                .take(1200)
                .collect::<String>()
        } else {
            format!("已保存 {filename}，Rust 后端将其作为格式说明文档保留；需要精细抽取时可继续由 Python 兼容层或后续 Rust 文档解析器处理。")
        };
        (
            "rules",
            "format_rules",
            Vec::new(),
            summary.clone(),
            summary.chars().count(),
        )
    };
    let record = json!({
        "id": template_id,
        "name": display_name.chars().take(80).collect::<String>(),
        "filename": filename,
        "suffix": suffix,
        "mode": mode,
        "kind": kind,
        "is_builtin": false,
        "created_at": Local::now().format("%Y-%m-%dT%H:%M:%S").to_string(),
        "placeholders": placeholders,
        "rule_items": [],
        "rule_summary": rule_summary,
        "extracted_chars": extracted_chars
    });
    let index_path = state.templates_root.join("index.json");
    let mut index = load_json_optional(&index_path)?
        .and_then(|value| value.as_array().cloned())
        .unwrap_or_default();
    index.push(record.clone());
    save_json(&index_path, &Value::Array(index))?;
    Ok(record)
}

fn validate_template_id(state: &AppState, template_id: &str) -> ApiResult<()> {
    if template_id == DEFAULT_TEMPLATE_ID {
        return Ok(());
    }
    for item in list_templates(state)? {
        if item.get("id").and_then(Value::as_str) == Some(template_id) {
            return Ok(());
        }
    }
    Err(ApiError::not_found("模板不存在"))
}

fn make_support_zip(root: &Path) -> ApiResult<PathBuf> {
    let archive_path = root.join("artifacts").join("support_materials.zip");
    if archive_path.exists() {
        fs::remove_file(&archive_path).map_err(io_error)?;
    }
    fs::create_dir_all(archive_path.parent().unwrap_or(root)).map_err(io_error)?;
    let file = File::create(&archive_path).map_err(io_error)?;
    let mut zip = zip::ZipWriter::new(file);
    let options = zip::write::SimpleFileOptions::default()
        .compression_method(zip::CompressionMethod::Deflated);
    for folder in ["artifacts", "paper", "code", "results"] {
        let source = root.join(folder);
        if !source.exists() {
            continue;
        }
        for entry in WalkDir::new(&source).into_iter().filter_map(Result::ok) {
            if !entry.file_type().is_file() {
                continue;
            }
            let path = entry.path();
            if path
                .file_name()
                .and_then(OsStr::to_str)
                .unwrap_or("")
                .ends_with(".zip")
            {
                continue;
            }
            let rel = path
                .strip_prefix(root)
                .map_err(|err| ApiError::internal(err.to_string()))?;
            let name = normalize_slashes(rel);
            zip.start_file(name, options).map_err(zip_error)?;
            let mut bytes = Vec::new();
            File::open(path)
                .map_err(io_error)?
                .read_to_end(&mut bytes)
                .map_err(io_error)?;
            zip.write_all(&bytes).map_err(io_error)?;
        }
    }
    zip.finish().map_err(zip_error)?;
    Ok(archive_path)
}

fn unpack_or_copy(upload_path: &Path, raw_dir: &Path) -> ApiResult<()> {
    fs::create_dir_all(raw_dir).map_err(io_error)?;
    let suffix = upload_path
        .extension()
        .and_then(OsStr::to_str)
        .unwrap_or("")
        .to_lowercase();
    if suffix == "zip" {
        let file = File::open(upload_path).map_err(io_error)?;
        let mut archive = ZipArchive::new(file).map_err(zip_error)?;
        if archive.len() > MAX_ZIP_ENTRIES {
            return Err(ApiError::bad_request(format!(
                "压缩包文件数过多，请控制在 {MAX_ZIP_ENTRIES} 个以内"
            )));
        }
        let mut unpacked_bytes = 0_u64;
        for i in 0..archive.len() {
            let mut file = archive.by_index(i).map_err(zip_error)?;
            if file.is_dir() {
                continue;
            }
            unpacked_bytes = unpacked_bytes.saturating_add(file.size());
            if unpacked_bytes > MAX_UNPACKED_BYTES {
                return Err(ApiError::bad_request(
                    "压缩包解压后过大，请控制在 500 MB 内",
                ));
            }
            let enclosed = file
                .enclosed_name()
                .ok_or_else(|| ApiError::bad_request("压缩包包含非法路径"))?
                .to_path_buf();
            let target = raw_dir.join(enclosed);
            ensure_inside(raw_dir, &target)?;
            fs::create_dir_all(target.parent().unwrap_or(raw_dir)).map_err(io_error)?;
            let mut out = File::create(&target).map_err(io_error)?;
            std::io::copy(&mut file, &mut out).map_err(io_error)?;
        }
    } else {
        let target = raw_dir.join(
            upload_path
                .file_name()
                .unwrap_or_else(|| OsStr::new("upload")),
        );
        fs::copy(upload_path, target).map_err(io_error)?;
    }
    Ok(())
}

fn load_json(path: &Path) -> ApiResult<Value> {
    let text = fs::read_to_string(path).map_err(io_error)?;
    serde_json::from_str(&text)
        .map_err(|err| ApiError::internal(format!("JSON 解析失败 {}: {err}", path.display())))
}

fn load_json_optional(path: &Path) -> ApiResult<Option<Value>> {
    if !path.exists() {
        return Ok(None);
    }
    Ok(Some(load_json(path)?))
}

fn save_json(path: &Path, value: &Value) -> ApiResult<()> {
    let parent = path.parent().unwrap_or_else(|| Path::new("."));
    fs::create_dir_all(parent).map_err(io_error)?;
    let text =
        serde_json::to_string_pretty(value).map_err(|err| ApiError::internal(err.to_string()))?;
    let file_name = path
        .file_name()
        .and_then(OsStr::to_str)
        .unwrap_or("data.json");
    let tmp_path = parent.join(format!(".{file_name}.{}.tmp", Uuid::new_v4().simple()));
    fs::write(&tmp_path, text).map_err(io_error)?;
    match fs::rename(&tmp_path, path) {
        Ok(()) => Ok(()),
        Err(err) if path.exists() => {
            fs::remove_file(path).map_err(io_error)?;
            fs::rename(&tmp_path, path).map_err(|rename_err| {
                let _ = fs::remove_file(&tmp_path);
                ApiError::internal(format!(
                    "JSON 写入失败：{rename_err}; 初始重命名错误：{err}"
                ))
            })
        }
        Err(err) => {
            let _ = fs::remove_file(&tmp_path);
            Err(io_error(err))
        }
    }
}

fn normalize_api_key(value: Option<String>) -> ApiResult<Option<String>> {
    let Some(value) = value else {
        return Ok(None);
    };
    let value = value.trim().to_string();
    if value.is_empty() {
        return Ok(None);
    }
    if value.chars().any(char::is_whitespace) {
        return Err(ApiError::bad_request("API Key 不能包含空白字符"));
    }
    if value.len() < 20 {
        return Err(ApiError::bad_request("API Key 长度过短"));
    }
    Ok(Some(value))
}

fn normalize_base_url(value: Option<String>) -> ApiResult<Option<String>> {
    let Some(value) = value else {
        return Ok(None);
    };
    let value = value.trim().trim_end_matches('/').to_string();
    if value.is_empty() {
        return Ok(Some(DEFAULT_BASE_URL.to_string()));
    }
    if !(value.starts_with("https://") || value.starts_with("http://")) {
        return Err(ApiError::bad_request(
            "Base URL 必须以 http:// 或 https:// 开头",
        ));
    }
    Ok(Some(value))
}

fn normalize_model(value: Option<String>) -> ApiResult<Option<String>> {
    let Some(value) = value else {
        return Ok(None);
    };
    let value = value.trim().to_string();
    if value.is_empty() {
        return Ok(Some(DEFAULT_MODEL.to_string()));
    }
    if value.chars().any(char::is_whitespace) {
        return Err(ApiError::bad_request("模型名称不能包含空白字符"));
    }
    Ok(Some(value))
}

fn mask_api_key(api_key: &str) -> String {
    if api_key.is_empty() {
        String::new()
    } else if api_key.len() <= 12 {
        "*".repeat(api_key.len())
    } else {
        format!("{}...{}", &api_key[..7], &api_key[api_key.len() - 4..])
    }
}

fn slugify(text: &str) -> String {
    let re = Regex::new(r"[^\w\-\u4e00-\u9fff]+").unwrap();
    let clean = re.replace_all(text, "-").trim_matches('-').to_string();
    clean
        .chars()
        .take(48)
        .collect::<String>()
        .if_empty("project")
}

fn find_placeholders(text: &str) -> Vec<String> {
    let re = Regex::new(r"__[A-Z0-9_]+__").unwrap();
    let mut items = re
        .find_iter(text)
        .map(|m| m.as_str().to_string())
        .collect::<Vec<_>>();
    items.sort();
    items.dedup();
    items
}

fn safe_relative_path(path: &str) -> ApiResult<PathBuf> {
    let normalized = path.replace('\\', "/");
    let candidate = PathBuf::from(normalized);
    let mut safe = PathBuf::new();
    for component in candidate.components() {
        match component {
            Component::Normal(part) => safe.push(part),
            Component::CurDir => {}
            _ => return Err(ApiError::bad_request("非法路径")),
        }
    }
    if safe.as_os_str().is_empty() {
        return Err(ApiError::bad_request("非法路径"));
    }
    Ok(safe)
}

fn ensure_inside(root: &Path, target: &Path) -> ApiResult<()> {
    let root = root.canonicalize().map_err(io_error)?;
    let parent = target
        .parent()
        .unwrap_or(root.as_path())
        .canonicalize()
        .unwrap_or_else(|_| root.clone());
    if parent == root || parent.starts_with(&root) {
        Ok(())
    } else {
        Err(ApiError::bad_request("非法路径"))
    }
}

fn file_name_only(path: &str) -> String {
    Path::new(path)
        .file_name()
        .and_then(OsStr::to_str)
        .unwrap_or("upload")
        .to_string()
}

fn normalize_slashes(path: impl AsRef<Path>) -> String {
    path.as_ref().to_string_lossy().replace('\\', "/")
}

fn content_disposition(file_name: &str) -> String {
    let fallback = ascii_filename_fallback(file_name);
    format!(
        "attachment; filename=\"{}\"; filename*=UTF-8''{}",
        fallback,
        percent_encode_utf8(file_name)
    )
}

fn ascii_filename_fallback(file_name: &str) -> String {
    let clean = file_name
        .chars()
        .map(|ch| {
            if ch.is_ascii_alphanumeric() || matches!(ch, '.' | '-' | '_') {
                ch
            } else {
                '_'
            }
        })
        .collect::<String>()
        .trim_matches('_')
        .to_string();
    clean.if_empty("download")
}

fn percent_encode_utf8(value: &str) -> String {
    value
        .as_bytes()
        .iter()
        .map(|byte| {
            if byte.is_ascii_alphanumeric() || matches!(*byte, b'.' | b'-' | b'_') {
                (*byte as char).to_string()
            } else {
                format!("%{byte:02X}")
            }
        })
        .collect()
}

fn files_len_from_raw(raw_dir: &Path) -> usize {
    WalkDir::new(raw_dir)
        .into_iter()
        .filter_map(Result::ok)
        .filter(|entry| entry.file_type().is_file())
        .count()
}

fn detect_command(version_cmd: &[&str], health_cmd: Option<&[&str]>) -> Value {
    if which(version_cmd[0]).is_none() {
        return json!({"available": false, "reason": format!("未找到 {}", version_cmd[0])});
    }
    let version = Command::new(version_cmd[0])
        .args(&version_cmd[1..])
        .output();
    let Ok(version) = version else {
        return json!({"available": false, "reason": "命令启动失败"});
    };
    let mut available = version.status.success();
    let mut detail = if version.stdout.is_empty() {
        String::from_utf8_lossy(&version.stderr).trim().to_string()
    } else {
        String::from_utf8_lossy(&version.stdout).trim().to_string()
    };
    if available {
        if let Some(cmd) = health_cmd {
            if let Ok(health) = Command::new(cmd[0]).args(&cmd[1..]).output() {
                available = health.status.success();
                if !available {
                    detail = String::from_utf8_lossy(&health.stderr).trim().to_string();
                }
            }
        }
    }
    json!({"available": available, "executable": which(version_cmd[0]).unwrap_or_default(), "detail": detail})
}

fn which(command: &str) -> Option<String> {
    let path_var = env::var_os("PATH")?;
    let extensions = if cfg!(windows) {
        vec![".exe", ".bat", ".cmd", ""]
    } else {
        vec![""]
    };
    for dir in env::split_paths(&path_var) {
        for ext in &extensions {
            let candidate = dir.join(format!("{command}{ext}"));
            if candidate.is_file() {
                return Some(candidate.to_string_lossy().to_string());
            }
        }
    }
    None
}

fn io_error(err: std::io::Error) -> ApiError {
    ApiError::internal(err.to_string())
}

fn zip_error(err: zip::result::ZipError) -> ApiError {
    ApiError::internal(err.to_string())
}

fn multipart_error(err: axum::extract::multipart::MultipartError) -> ApiError {
    ApiError::bad_request(err.to_string())
}

trait IfEmpty {
    fn if_empty(self, fallback: &str) -> String;
}

impl IfEmpty for String {
    fn if_empty(self, fallback: &str) -> String {
        if self.is_empty() {
            fallback.to_string()
        } else {
            self
        }
    }
}

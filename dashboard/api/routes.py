"""REST API for vault dashboard."""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from dashboard.services.pipeline_runner import get_job, start_single_video_ingest_async
from dashboard.services.single_video_writer import resolve_data_dir_for_vault
from dashboard.services.topic_sync import rebuild_vault_topics, sync_topics_after_ingest
from dashboard.services.vault_editor import delete_vault, update_vault_metadata
from dashboard.services.vault_factory import create_vault, read_vault_meta
from dashboard.services.vault_reader import VaultReader
from dashboard.services.vault_scanner import decode_vault_id, discover_vaults
from dashboard.services.vault_writer import delete_note, write_note

router = APIRouter(prefix="/api")


class CreateVaultBody(BaseModel):
    name: str = Field(..., min_length=1, max_length=80)
    description: str = Field(default="", max_length=600)


class UpdateVaultBody(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    description: str | None = Field(default=None, max_length=600)
    themes: list[str] | None = Field(default=None, description="Replace theme/topic labels")


class UpdateNoteBody(BaseModel):
    path: str = Field(..., description="Note path relative to vault")
    content: str = Field(..., description="Full markdown content including frontmatter")


class SingleVideoIngestBody(BaseModel):
    url: str = Field(..., description="Single YouTube video URL")
    vault_mode: str = Field(
        default="existing",
        description="existing | manual (new named vault) | auto (profile from first video)",
    )
    vault_id: str | None = Field(default=None, description="Required when vault_mode=existing")
    vault_name: str | None = Field(default=None, description="Required when vault_mode=manual")
    vault_description: str | None = Field(default=None, description="Optional for manual new vault")


@router.get("/vaults")
def get_vaults() -> dict:
    return {"vaults": discover_vaults()}


@router.get("/vaults/{vault_id}")
def get_vault(vault_id: str, lang: str = Query(default="el")) -> dict:
    vaults = discover_vaults()
    match = next((v for v in vaults if v["id"] == vault_id), None)
    if not match:
        raise HTTPException(status_code=404, detail="Vault not found")
    ui = "en" if lang == "en" else "el"
    if ui == "en" and match.get("description_en"):
        match = {**match, "description": match["description_en"]}
    elif ui == "el" and match.get("description_el"):
        match = {**match, "description": match["description_el"]}
    return match


@router.get("/vaults/{vault_id}/cover")
def get_vault_cover(vault_id: str) -> FileResponse:
    try:
        root = decode_vault_id(vault_id).resolve()
        from dashboard.services.vault_cover import cover_api_path, ensure_vault_cover

        rel = cover_api_path(root) or ensure_vault_cover(root)
        if not rel:
            raise HTTPException(status_code=404, detail="No cover image")
        target = (root / rel).resolve()
        if not str(target).startswith(str(root)) or not target.is_file():
            raise HTTPException(status_code=404, detail="Cover not found")
        return FileResponse(target, media_type="image/jpeg")
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.patch("/vaults/{vault_id}")
def patch_vault(vault_id: str, body: UpdateVaultBody) -> dict:
    """Edit vault name, description, and themes."""
    if body.name is None and body.description is None and body.themes is None:
        raise HTTPException(status_code=400, detail="Provide at least one field to update")
    try:
        meta = update_vault_metadata(
            vault_id,
            name=body.name,
            description=body.description,
            themes=body.themes,
        )
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    vaults = discover_vaults()
    match = next((v for v in vaults if v["id"] == vault_id), None)
    return {"meta": meta, "vault": match}


@router.delete("/vaults/{vault_id}")
def remove_vault(vault_id: str) -> dict:
    """Delete a dashboard-managed vault folder (data/* or Vaults/* only)."""
    try:
        return delete_vault(vault_id)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e


@router.post("/vaults/maintain-all")
def maintain_all_vaults_endpoint() -> dict:
    """Rebuild Topics hierarchy, meta descriptions, and covers for every vault."""
    from dashboard.services.vault_maintainer import maintain_all_vaults

    reports = maintain_all_vaults(skip_llm=True)
    return {"vaults": reports, "count": len(reports)}


@router.post("/vaults/{vault_id}/sync-topics")
def sync_vault_topics(vault_id: str) -> dict:
    """Rebuild Topics hierarchy from enriched JSON + legacy flat topic notes."""
    try:
        from dashboard.services.topic_sync import rebuild_vault_topics, vault_hierarchy_status

        vault_path = decode_vault_id(vault_id).resolve()
        data_dir = resolve_data_dir_for_vault(vault_path)
        meta = read_vault_meta(vault_path) or {}
        vault_name = meta.get("name") or vault_path.parent.name
        themes = meta.get("themes") or []
        theme_profile = meta.get("theme_profile") or "health"
        before = vault_hierarchy_status(vault_path)
        from dashboard.services.vault_maintainer import _enriched_filter_for_meta

        touched_list = rebuild_vault_topics(
            vault_path,
            data_dir,
            vault_name=vault_name,
            vault_themes=themes,
            theme_profile=theme_profile,
            use_llm=True,
            enriched_filter=_enriched_filter_for_meta(meta),
        )
        after = vault_hierarchy_status(vault_path)
        return {
            "synced": len(touched_list),
            "topics": sorted(touched_list),
            "hierarchy": after,
            "migrated": before.get("needs_migration") and not after.get("needs_migration"),
        }
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.get("/vaults/{vault_id}/graph")
def get_graph(
    vault_id: str,
    scope: str = Query("overview", description="overview | theme | subtopic | full"),
    focus: str = Query("", description="Theme folder or note path for scoped graph"),
) -> dict:
    """Local graph of wikilink connections (Obsidian-style)."""
    try:
        reader = VaultReader(vault_id)
        return reader.build_graph(scope=scope, focus=focus)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.put("/vaults/{vault_id}/note")
def put_note(vault_id: str, body: UpdateNoteBody) -> dict:
    try:
        return write_note(vault_id, body.path, body.content)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e


@router.delete("/vaults/{vault_id}/note")
def remove_note(vault_id: str, path: str = Query(...)) -> dict:
    try:
        return delete_note(vault_id, path)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e


@router.get("/vaults/{vault_id}/tree")
def get_tree(vault_id: str, lang: str = Query(default="el")) -> dict:
    try:
        reader = VaultReader(vault_id)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    return {"tree": reader.list_tree(lang=lang)}


@router.get("/vaults/{vault_id}/notes")
def get_notes(
    vault_id: str,
    folder: str = Query(default="", description="Folder path relative to vault root"),
    flat: bool = Query(default=False),
    lang: str = Query(default="el"),
) -> dict:
    try:
        reader = VaultReader(vault_id)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    if flat:
        return {"notes": reader.list_all_notes_flat(lang=lang)}
    return {"notes": reader.list_notes(folder)}


@router.get("/vaults/{vault_id}/note")
def get_note(
    vault_id: str,
    path: str = Query(..., description="Note path relative to vault"),
    lang: str = Query(default="el"),
) -> dict:
    try:
        reader = VaultReader(vault_id)
        return reader.read_note(path, lang=lang)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e


@router.get("/vaults/{vault_id}/resolve")
def resolve_link(vault_id: str, target: str = Query(...)) -> dict:
    try:
        reader = VaultReader(vault_id)
        return reader.resolve_wikilink(target)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.get("/vaults/{vault_id}/backlinks")
def get_backlinks(vault_id: str, path: str = Query(...)) -> dict:
    try:
        reader = VaultReader(vault_id)
        return {"backlinks": reader.backlinks(path)}
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e


@router.get("/vaults/{vault_id}/asset")
def get_asset(vault_id: str, path: str = Query(...)) -> FileResponse:
    try:
        root = decode_vault_id(vault_id).resolve()
        rel = path.lstrip("/").replace("\\", "/")
        target = (root / rel).resolve()
        if not str(target).startswith(str(root)) or not target.is_file():
            raise HTTPException(status_code=404, detail="Asset not found")
        return FileResponse(target)
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.post("/vaults")
def create_vault_endpoint(body: CreateVaultBody) -> dict:
    """Create an empty vault with name and description (no video yet)."""
    try:
        vault = create_vault(name=body.name.strip(), description=body.description.strip(), source="manual")
        return {"vault": vault}
    except FileExistsError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e


@router.post("/ingest/single-video")
def ingest_single_video(body: SingleVideoIngestBody) -> dict:
    url = body.url.strip()
    if not url:
        raise HTTPException(status_code=400, detail="URL is required")

    mode = (body.vault_mode or "existing").strip().lower()
    if mode not in ("existing", "manual", "auto"):
        raise HTTPException(status_code=400, detail="vault_mode must be existing, manual, or auto")

    if mode == "existing":
        if not body.vault_id:
            raise HTTPException(status_code=400, detail="vault_id required for existing vault")
        vaults = discover_vaults()
        if not any(v["id"] == body.vault_id for v in vaults):
            raise HTTPException(status_code=404, detail="Vault not found")
    elif mode == "manual" and not (body.vault_name or "").strip():
        raise HTTPException(status_code=400, detail="vault_name required for manual new vault")

    job_id = start_single_video_ingest_async(
        url,
        body.vault_id,
        vault_mode=mode,
        vault_name=body.vault_name,
        vault_description=body.vault_description,
    )
    return {"job_id": job_id, "status": "queued", "vault_mode": mode}


@router.get("/ingest/jobs/{job_id}")
def ingest_job_status(job_id: str) -> dict:
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job

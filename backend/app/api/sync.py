from fastapi import APIRouter, HTTPException, Depends
from typing import Dict, Any

from backend.app.services.scheme_sync_service import SchemeSyncService

router = APIRouter(prefix="/api/rag", tags=["RAG Synchronization"])
_service = None


def get_sync_service() -> SchemeSyncService:
    global _service
    if _service is None:
        _service = SchemeSyncService()
    return _service


@router.post("/sync")
def trigger_rag_sync(service: SchemeSyncService = Depends(get_sync_service)) -> Dict[str, Any]:
    """
    Synchronizes new and updated cleaned schemes from MySQL into Qdrant vector database.
    - Case A: New Scheme -> Insert & Index
    - Case B: Existing Unchanged -> Skip
    - Case C: Existing Updated -> Replace vectors & update hash
    - Case D: Missing from Source -> Flag as REVIEW_REQUIRED
    """
    try:
        results = service.run_synchronization()
        return {
            "status": "SUCCESS",
            "message": "RAG synchronization completed successfully.",
            "data": results
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Synchronization failed: {str(e)}")


@router.get("/status")
def get_rag_status(service: SchemeSyncService = Depends(get_sync_service)) -> Dict[str, Any]:
    """
    Returns synchronization statistics: total SQL schemes, indexed schemes,
    unchanged schemes, pending schemes, and failed schemes.
    """
    try:
        stats = service.get_sync_status()
        return {
            "status": "SUCCESS",
            "data": stats
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch status: {str(e)}")


@router.get("/scheme/{scheme_id}")
def get_scheme_sync_status(scheme_id: int, service: SchemeSyncService = Depends(get_sync_service)) -> Dict[str, Any]:
    """
    Returns indexing status, content hash, and source information for a specific scheme.
    """
    record = service.get_scheme_detail(scheme_id)
    if not record:
        raise HTTPException(status_code=404, detail=f"Scheme with ID {scheme_id} not found in synchronization records.")
    return {
        "status": "SUCCESS",
        "data": record
    }

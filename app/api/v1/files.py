"""File endpoints. Thin on purpose: read bytes, call the service, shape the reply."""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, File, Query, UploadFile, status
from starlette.concurrency import run_in_threadpool

from app.api.dependencies import get_file_service
from app.api.schemas import FileOut, MeasurementPageOut
from app.services.file_service import FileService

router = APIRouter(tags=["files"])

ServiceDep = Annotated[FileService, Depends(get_file_service)]

DEFAULT_PAGE_SIZE = 100
MAX_PAGE_SIZE = 1000


@router.post(
    "/files/",
    response_model=FileOut,
    status_code=status.HTTP_201_CREATED,
    summary="Upload a KML or zipped Shapefile and process it",
)
async def upload_file(
    service: ServiceDep,
    file: Annotated[UploadFile, File(description="A .kml file or a .zip Shapefile")],
) -> FileOut:
    # Read one byte past the limit so an oversized upload is detected without
    # loading all of it into memory.
    content = await file.read(service.max_upload_size_bytes + 1)
    # Processing is CPU-bound and synchronous, so it runs in a worker thread
    # to keep the event loop free (until Step 11 moves it to a job queue).
    record = await run_in_threadpool(service.ingest, file.filename or "", content)
    return FileOut.from_record(record)


@router.get(
    "/files/{file_id}/",
    response_model=FileOut,
    summary="Get a file's status and metadata",
)
def get_file(file_id: str, service: ServiceDep) -> FileOut:
    return FileOut.from_record(service.get(file_id))


@router.get(
    "/files/{file_id}/measurements/",
    response_model=MeasurementPageOut,
    summary="Get per-feature measurements (paged)",
)
def get_measurements(
    file_id: str,
    service: ServiceDep,
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = DEFAULT_PAGE_SIZE,
    offset: Annotated[int, Query(ge=0)] = 0,
    status_filter: Annotated[
        Literal["measured", "skipped", "failed"] | None,
        Query(alias="status", description="Only features with this outcome"),
    ] = None,
) -> MeasurementPageOut:
    record, page = service.list_measurements(
        file_id, offset=offset, limit=limit, status=status_filter
    )
    return MeasurementPageOut.build(record, page)
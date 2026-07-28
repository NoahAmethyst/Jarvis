import asyncio
import logging
import uvicorn
from jarvis.config import HTTP_PORT, GRPC_PORT
from jarvis.api.http.routes import app
from jarvis.api.grpc.server import create_grpc_server
from jarvis.logging_config import configure_logging
from jarvis.memory.conversation import init_db
from jarvis.memory.knowledge import init_collection
from jarvis.startup_checks import run_model_startup_checks

logger = logging.getLogger(__name__)


async def serve():
    configure_logging()
    try:
        run_model_startup_checks()
    except Exception:
        logger.error("Model startup checks failed category=internal")

    logger.info("Initializing storage...")
    init_db()
    init_collection()

    grpc_server = await create_grpc_server()
    await grpc_server.start()
    logger.info("gRPC server listening on :%d", GRPC_PORT)

    config = uvicorn.Config(
        app,
        host="0.0.0.0",
        port=HTTP_PORT,
        log_level="info",
        log_config=None,
    )
    http_server = uvicorn.Server(config)
    logger.info("HTTP server starting on :%d", HTTP_PORT)

    await asyncio.gather(
        http_server.serve(),
        grpc_server.wait_for_termination(),
    )


if __name__ == "__main__":
    asyncio.run(serve())

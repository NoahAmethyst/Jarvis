import asyncio
import logging
import uvicorn
from jarvis.config import HTTP_PORT, GRPC_PORT
from jarvis.api.http.routes import app
from jarvis.api.grpc.server import create_grpc_server
from jarvis.logging_config import configure_logging, format_log_tags
from jarvis.memory.conversation import init_db
from jarvis.memory.knowledge import init_collection
from jarvis.startup_checks import run_model_startup_checks

logger = logging.getLogger(__name__)


async def serve():
    app.state.ready = False
    configure_logging()
    try:
        run_model_startup_checks()
    except Exception:
        logger.error(
            "%s Unexpected startup check failure",
            format_log_tags(
                ("组件", "模型启动检查"),
                ("结果", "失败"),
                ("类别", "internal"),
            ),
        )

    logger.info(
        "%s Initializing storage",
        format_log_tags(("组件", "存储"), ("状态", "初始化")),
    )
    init_db()
    init_collection()

    grpc_server = await create_grpc_server()
    await grpc_server.start()
    logger.info(
        "%s Server listening",
        format_log_tags(
            ("服务", "gRPC"),
            ("端口", GRPC_PORT),
            ("状态", "就绪"),
        ),
    )
    app.state.ready = True

    config = uvicorn.Config(
        app,
        host="0.0.0.0",
        port=HTTP_PORT,
        log_level="info",
        log_config=None,
    )
    http_server = uvicorn.Server(config)
    logger.info(
        "%s Server starting",
        format_log_tags(
            ("服务", "HTTP"),
            ("端口", HTTP_PORT),
            ("状态", "启动"),
        ),
    )

    await asyncio.gather(
        http_server.serve(),
        grpc_server.wait_for_termination(),
    )


if __name__ == "__main__":
    asyncio.run(serve())

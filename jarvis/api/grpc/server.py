import grpc
from jarvis.api.grpc import jarvis_pb2_grpc
from jarvis.api.grpc.servicer import JarvisServicer
from jarvis.config import GRPC_PORT


async def create_grpc_server() -> grpc.aio.Server:
    server = grpc.aio.server()
    jarvis_pb2_grpc.add_JarvisServiceServicer_to_server(JarvisServicer(), server)
    server.add_insecure_port(f"[::]:{GRPC_PORT}")
    return server

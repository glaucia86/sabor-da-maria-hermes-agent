"""Seam legado para regressões com fixtures; nunca conectar ao atendimento."""

import asyncio
import logging
import os
from pathlib import Path

from dona_maria.mcp_server import serve

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    logging.info('{"event":"startup","message":"Servidor Dona Maria iniciado em stdio."}')
    asyncio.run(serve(Path(os.environ["DONA_MARIA_DB_PATH"])))

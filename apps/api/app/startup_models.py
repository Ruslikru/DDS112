"""Start the three inference paths without delaying the application UI."""
import asyncio
from .diagnostics import event

async def warm_models():
    from local_ai.engine import engine,assistant_engine
    from .voice import runtime
    async def warm(name,loader):
        try:
            await asyncio.to_thread(loader)
            event('model_warm_ready',model=name)
        except Exception as error:
            event('model_warm_failed',model=name,error=str(error))
    def start(model):
        with model.lock:model.start()
    await asyncio.gather(warm('карточки',lambda:start(engine)),
                         warm('ассистент и анализ',lambda:start(assistant_engine)),
                         warm('распознавание и голоса',runtime.warm))

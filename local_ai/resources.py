"""Per-device CPU budget for the three bundled models."""
import os


def cpu_threads():
    return max(1, os.cpu_count() or 1)


def automatic_threads(total=None):
    total=max(1, total or cpu_threads())
    # Leave spare capacity on larger PCs. Tiny PCs share one thread per model.
    speech=2 if total>=8 else 1
    available=max(1,total-2*speech)
    qwen=8 if available>=8 else 6 if available>=6 else 4 if available>=4 else available
    return {'threads':qwen,'stt_threads':speech,'tts_threads':speech}


def effective_resources(config):
    total=cpu_threads()
    values=automatic_threads(total) if config.get('threads_auto',True) else {
        key:max(1,min(total,int(config.get(key,default))))
        for key,default in automatic_threads(total).items()}
    return {**values,'cpu_threads':total,'threads_auto':config.get('threads_auto',True),
            'recommended_threads':automatic_threads(total)}

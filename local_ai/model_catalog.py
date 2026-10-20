"""The application ships one shared text model. Legacy names support offline training tools."""
CARD_MODEL = 'models/Qwen3-4B-Instruct-2507-Q4_K_M.gguf'
ASSISTANT_MODEL = 'models/Qwen2.5-1.5B-Instruct-Q4_K_M.gguf'
ASSISTANT_ADAPTER = 'models/qwen-dds-1000-f32.gguf'
MODELS = {
    CARD_MODEL: 'Qwen3 4B Instruct · общая текстовая модель',
}
MODEL_FILES = (CARD_MODEL,)


def model_files(model):
    return (model,)


def model_available(root, model):
    return model in MODELS and all((root / name).is_file() for name in model_files(model))

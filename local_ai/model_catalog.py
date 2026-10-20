"""Models shipped with the application, including the trained assistant adapter."""
CARD_MODEL = 'models/Qwen3-4B-Instruct-2507-Q4_K_M.gguf'
ASSISTANT_MODEL = 'models/Qwen2.5-1.5B-Instruct-Q4_K_M.gguf'
ASSISTANT_ADAPTER = 'models/qwen-dds-1000-f32.gguf'
MODELS = {
    CARD_MODEL: 'Qwen3 4B Instruct · генерация карточек',
    ASSISTANT_MODEL: 'Qwen 2.5 1.5B Instruct · обучение 1000 шагов',
}
MODEL_FILES = (CARD_MODEL, ASSISTANT_MODEL, ASSISTANT_ADAPTER)


def model_files(model):
    return (model, ASSISTANT_ADAPTER) if model == ASSISTANT_MODEL else (model,)


def model_available(root, model):
    return model in MODELS and all((root / name).is_file() for name in model_files(model))

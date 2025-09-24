# gui/models/stt_models.py
import os
import json

def load_installed_stt_models(base_path):
    """
    Load installed STT models by scanning the stt-models directory
    and mapping found directories back to size names using stt.json

    Args:
        base_path: Path to the .assistivox directory

    Returns:
        dict: Model groups with installed sizes, e.g. {"vosk": ["small"], "faster-whisper": ["tiny", "base"]}
    """
    model_groups = {}
    stt_models_path = os.path.join(base_path, "stt-models")

    if not os.path.exists(stt_models_path):
        return model_groups

    # Load MODEL_MAP from stt.json
    try:
        # Get the project root directory (3 levels up from gui/models/)
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        stt_json_path = os.path.join(project_root, "stt.json")

        with open(stt_json_path, 'r') as f:
            stt_data = json.load(f)

        # Create MODEL_MAP from loaded data
        MODEL_MAP = {}
        for model_type, sizes in stt_data.items():
            MODEL_MAP[model_type] = {}
            for size, info in sizes.items():
                MODEL_MAP[model_type][size] = info["model_id"]
    except Exception as e:
        print(f"Error loading stt.json: {e}")
        MODEL_MAP = {}

    for model_group in os.listdir(stt_models_path):
        group_path = os.path.join(stt_models_path, model_group)
        if not os.path.isdir(group_path):
            continue

        sizes = []

        # Get the model mapping for this group from MODEL_MAP
        if model_group in MODEL_MAP:
            # Create reverse mapping: model_id -> size
            size_lookup = {model_id: size for size, model_id in MODEL_MAP[model_group].items()}

            if model_group == "faster-whisper":
                # For faster-whisper, check nested structure
                def check_nested_model(path):
                    found_sizes = []
                    for item in os.listdir(path):
                        item_path = os.path.join(path, item)
                        if os.path.isdir(item_path):
                            # Check if this contains model files
                            model_files = ['config.json', 'model.bin', 'tokenizer.json']
                            if all(os.path.exists(os.path.join(item_path, f)) for f in model_files):
                                # This looks like a model directory, check parent name
                                parent_name = os.path.basename(item_path)
                                # Look for size based on model name pattern
                                for model_id, size in size_lookup.items():
                                    if parent_name in model_id or model_id.endswith(parent_name):
                                        found_sizes.append(size)
                            else:
                                # Recurse into subdirectories
                                found_sizes.extend(check_nested_model(item_path))
                    return found_sizes

                sizes = check_nested_model(group_path)

            elif model_group == "vosk":
                # For vosk, check if it contains model files
                for model_dir in os.listdir(group_path):
                    model_dir_path = os.path.join(group_path, model_dir)
                    if os.path.isdir(model_dir_path):
                        if os.path.exists(os.path.join(model_dir_path, "am")):
                            # Look up the size using the model_id
                            if model_dir in size_lookup:
                                sizes.append(size_lookup[model_dir])
            else:
                # For other models, check if directory name matches a model_id
                for model_dir in os.listdir(group_path):
                    model_dir_path = os.path.join(group_path, model_dir)
                    if os.path.isdir(model_dir_path):
                        if model_dir in size_lookup:
                            sizes.append(size_lookup[model_dir])

        # Remove duplicates and sort
        if sizes:
            model_groups[model_group] = sorted(list(set(sizes)))

    return model_groups

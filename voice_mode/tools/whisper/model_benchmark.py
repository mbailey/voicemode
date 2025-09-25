"""MCP tool for benchmarking Whisper models."""

from typing import Union, List, Dict, Any, Optional
from voice_mode.tools.whisper.models import (
    get_installed_whisper_models,
    benchmark_whisper_model,
    is_whisper_model_installed,
    WHISPER_MODEL_REGISTRY
)


async def whisper_model_benchmark(
    models: Union[str, List[str]] = "installed",
    sample_file: Optional[str] = None,
    runs: int = 1
) -> Dict[str, Any]:
    """Benchmark Whisper model performance.
    
    Args:
        models: 'installed' (default), 'all', specific model name, or list of models
        sample_file: Optional audio file for testing (uses default JFK sample if None)
        runs: Number of benchmark runs per model (default: 1)
        
    Returns:
        Dict with benchmark results and recommendations
    """
    # Determine which models to benchmark
    if models == "installed":
        model_list = get_installed_whisper_models()
        if not model_list:
            return {
                "success": False,
                "error": "No Whisper models are installed. Install models first with whisper_model_install()"
            }
    elif models == "all":
        # Only benchmark installed models from the full list
        all_models = list(WHISPER_MODEL_REGISTRY.keys())
        model_list = [m for m in all_models if is_whisper_model_installed(m)]
        if not model_list:
            return {
                "success": False,
                "error": "No Whisper models are installed"
            }
    elif isinstance(models, str):
        # Single model specified
        if not is_whisper_model_installed(models):
            return {
                "success": False,
                "error": f"Model {models} is not installed"
            }
        model_list = [models]
    elif isinstance(models, list):
        # List of models specified
        model_list = []
        for model in models:
            if is_whisper_model_installed(model):
                model_list.append(model)
            else:
                # Model not installed, skip silently or could use logger.warning
                pass
        if not model_list:
            return {
                "success": False,
                "error": "None of the specified models are installed"
            }
    else:
        return {
            "success": False,
            "error": f"Invalid models parameter: {models}"
        }
    
    # Run benchmarks
    results = []
    failed = []
    
    for model in model_list:
        best_result = None
        
        for run_num in range(runs):
            result = benchmark_whisper_model(model, sample_file)
            
            if result.get("success"):
                # Keep the best (fastest) result from multiple runs
                if best_result is None or result["total_time_ms"] < best_result["total_time_ms"]:
                    best_result = result
            else:
                # If any run fails, record the failure
                if model not in failed:
                    failed.append(model)
                    results.append({
                        "model": model,
                        "success": False,
                        "error": result.get("error", "Benchmark failed")
                    })
                break
        
        if best_result:
            results.append(best_result)
    
    if not results:
        return {
            "success": False,
            "error": "No benchmarks completed successfully"
        }
    
    # Find successful results for analysis
    successful_results = [r for r in results if r.get("success")]
    
    if successful_results:
        # Find fastest model
        fastest = min(successful_results, key=lambda x: x["total_time_ms"])
        
        # Generate recommendations based on results
        recommendations = []
        
        # Categorize by speed
        for result in successful_results:
            rtf = result.get("real_time_factor", 0)
            if rtf > 20:
                category = "Ultra-fast (good for real-time)"
            elif rtf > 5:
                category = "Fast (good for interactive use)"
            elif rtf > 1:
                category = "Moderate (good balance)"
            else:
                category = "Slow (best accuracy)"
            
            result["category"] = category
        
        # Generate specific recommendations
        if fastest["real_time_factor"] > 10:
            recommendations.append(f"Use {fastest['model']} for real-time applications")
        
        # Find best balance (medium or base if available)
        balance_models = [r for r in successful_results if r["model"] in ["base", "medium"]]
        if balance_models:
            best_balance = min(balance_models, key=lambda x: x["total_time_ms"])
            recommendations.append(f"Use {best_balance['model']} for balanced speed/accuracy")
        
        # Recommend large models for accuracy
        large_models = [r for r in successful_results if "large" in r["model"]]
        if large_models:
            best_large = min(large_models, key=lambda x: x["total_time_ms"])
            recommendations.append(f"Use {best_large['model']} for best accuracy")
    else:
        fastest = None
        recommendations = ["Unable to generate recommendations - no successful benchmarks"]
    
    return {
        "success": True,
        "benchmarks": results,
        "models_tested": len(model_list),
        "models_failed": len(failed),
        "fastest_model": fastest["model"] if fastest else None,
        "fastest_time_ms": fastest["total_time_ms"] if fastest else None,
        "recommendations": recommendations,
        "sample_file": sample_file or "default JFK sample",
        "runs_per_model": runs
    }
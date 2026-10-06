"""Small hosted API checks; never print credentials or raw service responses."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import math
from pathlib import Path
import urllib.error
import urllib.request

from dotenv import dotenv_values


def check(name, url, payload, key, timeout):
    request = urllib.request.Request(
        url, data=json.dumps(payload).encode(), method="POST",
        headers={"Authorization": "Bearer " + key,
                 "Content-Type": "application/json", "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            status = response.status
            if status != 200:
                return {"service": name, "http": status, "inference_verified": False}
            data = json.load(response)
        if name == "embedding":
            rows = data.get("data", [])
            vector = rows[0].get("embedding", []) if len(rows) == 1 else []
            valid = bool(vector) and all(
                isinstance(x, (float, int)) and not isinstance(x, bool) and math.isfinite(x)
                for x in vector)
            return {"service": name, "http": status, "inference_verified": valid,
                    "dimensions": len(vector)}
        molecules = data.get("molecules")
        if isinstance(molecules, str):
            molecules = json.loads(molecules)
        compatible = (isinstance(molecules, list) and bool(molecules)
                      and all(isinstance(x, dict) and isinstance(x.get("sample"), str)
                              and x["sample"] for x in molecules))
        return {"service": name, "http": status,
                "upstream_response_compatible": compatible,
                "molecule_count": len(molecules) if isinstance(molecules, list) else 0}
    except urllib.error.HTTPError as error:
        return {"service": name, "http": error.code, "inference_verified": False}
    except Exception as error:
        # Error text and response bodies can contain credentials: print type only.
        return {"service": name, "error_type": type(error).__name__,
                "inference_verified": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path,
                        default=Path(__file__).resolve().parents[1] / ".env")
    parser.add_argument("--timeout", type=float, default=45)
    args = parser.parse_args()
    if not math.isfinite(args.timeout) or args.timeout <= 0:
        parser.error("timeout must be finite and positive")
    key = dotenv_values(args.env_file).get("NVIDIA_API_KEY")
    if not key:
        parser.error("NVIDIA_API_KEY is missing in the env file")
    probes = [
        ("embedding", "https://integrate.api.nvidia.com/v1/embeddings",
         {"model": "nvidia/nemotron-3-embed-1b", "input": ["Cystic fibrosis CFTR gene therapy"],
          "input_type": "passage", "encoding_format": "float"}),
        ("molmim", "https://health.api.nvidia.com/v1/biology/nvidia/molmim/generate",
         {"smi": "CC(=O)OC1=CC=CC=C1C(=O)O", "num_molecules": 1,
          "algorithm": "CMA-ES", "property_name": "QED", "iterations": 1,
          "min_similarity": 0.7}),
    ]
    print("Sending one embedding request and one small MolMIM request; no retries.", flush=True)
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(check, name, url, payload, key, args.timeout)
                   for name, url, payload in probes]
        summaries = [future.result() for future in futures]
    for summary in summaries:
        print(json.dumps(summary, ensure_ascii=False))
    print("DiffDock: not tested; requires a real protein/ligand fixture.")
    return 0 if (summaries[0].get("inference_verified")
                 and summaries[1].get("upstream_response_compatible")) else 1


if __name__ == "__main__":
    raise SystemExit(main())

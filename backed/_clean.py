import shutil, os

ROOT = os.path.dirname(os.path.abspath(__file__))
SING = ["articles", "publications", "accounts", "jobs", "tasks"]

for name in SING:
    paths = [
        os.path.join(ROOT, "models", name + ".py"),
        os.path.join(ROOT, "schemas", name + ".py"),
        os.path.join(ROOT, "repository", name + "_repository.py"),
        os.path.join(ROOT, "service", name + "_service.py"),
        os.path.join(ROOT, "api", "v1", name),
        os.path.join(ROOT, "tests", "unit", f"test_{name}_service.py"),
        os.path.join(ROOT, "tests", "integration", "api", "v1", f"test_{name}.py"),
    ]
    for p in paths:
        if os.path.isdir(p):
            shutil.rmtree(p)
        elif os.path.isfile(p):
            os.remove(p)
print("cleaned singular outputs")

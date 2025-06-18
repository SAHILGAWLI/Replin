import os
import re
import sys
from collections import defaultdict

def extract_imports(file_path):
    """Extract all import statements from a Python file."""
    imports = set()
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
            
            # Find all import statements
            import_lines = re.findall(r'^import\s+(.*?)$|^from\s+(.*?)\s+import', content, re.MULTILINE)
            
            for imp in import_lines:
                # Handle 'import x' and 'from x import y'
                module = imp[0] if imp[0] else imp[1]
                # Get base module (before any dots)
                base_module = module.split('.')[0].strip()
                if base_module and not base_module.startswith('_'):  # Skip private modules
                    imports.add(base_module)
    except Exception as e:
        print(f"Error processing {file_path}: {e}")
    
    return imports

def get_stdlib_modules():
    """Get a list of Python standard library modules."""
    import stdlib_list
    return set(stdlib_list.stdlib_list("3.9"))

def main():
    # Directories to exclude
    exclude_dirs = ['venv', '.git', '__pycache__', '.qodo']
    
    # Get all Python files in the current directory and subdirectories
    python_files = []
    for root, dirs, files in os.walk('.'):
        # Skip excluded directories
        dirs[:] = [d for d in dirs if d not in exclude_dirs]
        
        for file in files:
            if file.endswith('.py'):
                python_files.append(os.path.join(root, file))
    
    # Extract imports from all files
    all_imports = set()
    file_imports = defaultdict(set)
    
    print(f"Analyzing {len(python_files)} Python files...")
    
    for file_path in python_files:
        imports = extract_imports(file_path)
        file_imports[file_path] = imports
        all_imports.update(imports)
    
    # Get standard library modules to exclude
    stdlib = get_stdlib_modules()
    
    # Filter out standard library modules
    third_party_imports = all_imports - stdlib
    
    # Read current requirements.txt
    current_reqs = set()
    try:
        with open('requirements.txt', 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):
                    # Extract package name (before any version specifier)
                    package = line.split('>=')[0].split('==')[0].split('<')[0].strip()
                    current_reqs.add(package)
    except FileNotFoundError:
        print("requirements.txt not found")
    
    # Common package name mappings (import name -> pip package name)
    mappings = {
        'PIL': 'pillow',
        'sklearn': 'scikit-learn',
        'bs4': 'beautifulsoup4',
        'dotenv': 'python-dotenv',
        'yaml': 'pyyaml',
        'cv2': 'opencv-python',
        'llama_index': 'llama-index-core',
        'livekit': 'livekit',
        'fastapi': 'fastapi',
        'pydantic': 'pydantic',
        'uvicorn': 'uvicorn',
        'openai': 'openai',
        'rtc': 'livekit',
    }
    
    # Check for potentially missing packages
    missing_packages = set()
    for imp in third_party_imports:
        # Apply mappings
        package_name = mappings.get(imp, imp)
        
        # Check if any existing requirement starts with this package
        found = False
        for req in current_reqs:
            if req.startswith(package_name) or package_name.startswith(req):
                found = True
                break
        
        if not found:
            missing_packages.add(package_name)
    
    # Print results
    print("\n=== IMPORT ANALYSIS RESULTS ===\n")
    
    if missing_packages:
        print("Potentially missing packages:")
        for package in sorted(missing_packages):
            print(f"  - {package}")
        print("\nThese packages appear in imports but might not be in requirements.txt.")
        print("Verify if they're needed or if they're dependencies of other packages.")
    else:
        print("No potentially missing packages found!")
    
    print("\n=== THIRD PARTY IMPORTS FOUND ===\n")
    for imp in sorted(third_party_imports):
        print(f"  - {imp}")

    print("\n=== CURRENT REQUIREMENTS ===\n")
    for req in sorted(current_reqs):
        print(f"  - {req}")

if __name__ == "__main__":
    main()

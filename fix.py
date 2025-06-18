#!/usr/bin/env python3
"""
Generate Comprehensive Requirements File

This script scans all Python files in the project directory to identify 
all imported libraries and generates a comprehensive requirements.txt file.
"""

import os
import sys
import ast
import pkg_resources
import re
import subprocess
from collections import defaultdict

def find_imports_in_file(file_path):
    """Extract all import statements from a Python file"""
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as file:
            content = file.read()
            
        try:
            tree = ast.parse(content)
            imports = set()
            
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for name in node.names:
                        imports.add(name.name.split('.')[0])
                elif isinstance(node, ast.ImportFrom):
                    if node.module:
                        imports.add(node.module.split('.')[0])
            
            return imports
        except SyntaxError:
            print(f"Syntax error in {file_path}, parsing imports using regex")
            # Fall back to regex for files with syntax errors
            import_regex = r'^import\s+(\w+)|^from\s+(\w+)'
            matches = re.findall(import_regex, content, re.MULTILINE)
            imports = set()
            for match in matches:
                if match[0]:
                    imports.add(match[0])
                if match[1]:
                    imports.add(match[1])
            return imports
            
    except Exception as e:
        print(f"Error processing {file_path}: {str(e)}")
        return set()

def is_standard_library(module_name):
    """Check if a module is part of the Python standard library"""
    try:
        module_path = __import__(module_name).__file__
        if module_path is None:
            return True  # Built-in modules have __file__ = None
        return "site-packages" not in module_path and "dist-packages" not in module_path
    except (ImportError, AttributeError):
        # If we can't import it, assume it's not standard library
        return False

def find_all_py_files(directory):
    """Find all Python files in the given directory and subdirectories"""
    py_files = []
    for root, dirs, files in os.walk(directory):
        # Skip virtual environments
        if 'venv' in dirs:
            dirs.remove('venv')
        if '.venv' in dirs:
            dirs.remove('.venv')
        if '__pycache__' in dirs:
            dirs.remove('__pycache__')
            
        for file in files:
            if file.endswith('.py'):
                py_files.append(os.path.join(root, file))
    return py_files

def get_installed_packages():
    """Get a dictionary of installed packages and their versions"""
    installed_packages = {}
    for package in pkg_resources.working_set:
        installed_packages[package.key] = package.version
    return installed_packages

def normalize_package_name(name):
    """Normalize package name to match PyPI convention"""
    name = name.lower().replace('_', '-')
    # Special case mappings
    mapping = {
        'PIL': 'pillow',
        'sklearn': 'scikit-learn',
        'cv2': 'opencv-python',
        'livekit-server-sdk': 'livekit-api',  # Special case for your livekit issue
    }
    return mapping.get(name, name)

def map_import_to_package(import_name):
    """Map import name to package name"""
    mapping = {
        'PIL': 'pillow',
        'sklearn': 'scikit-learn',
        'cv2': 'opencv-python',
        'yaml': 'pyyaml',
        'bs4': 'beautifulsoup4',
        'dotenv': 'python-dotenv',
        'livekit': 'livekit',
        'livekit_api': 'livekit-api',
        'livekit_server_sdk': 'livekit-api',
        'rtc': 'livekit',
        'llama_index': 'llama-index-core',
    }
    return mapping.get(import_name, import_name)

def generate_requirements_file(imports, installed_packages, output_file='requirements.txt'):
    """Generate a requirements.txt file from the list of imports"""
    with open(output_file, 'w') as f:
        f.write("# Generated requirements file\n")
        f.write("# Install with: pip install -r requirements.txt\n\n")
        
        # Sort the imports for readability
        known_packages = []
        unknown_packages = []
        
        for import_name in sorted(imports):
            package_name = map_import_to_package(import_name)
            norm_name = normalize_package_name(package_name)
            
            if norm_name in installed_packages:
                version = installed_packages[norm_name]
                known_packages.append(f"{norm_name}=={version}")
            else:
                # Try to find if it's a subpackage of an installed package
                found = False
                for installed_pkg in installed_packages:
                    try:
                        pkg_info = pkg_resources.get_distribution(installed_pkg)
                        if norm_name in [normalize_package_name(p) for p in pkg_info._get_metadata('top_level.txt').split()]:
                            found = True
                            known_packages.append(f"{installed_pkg}=={installed_packages[installed_pkg]}")
                            break
                    except Exception:
                        continue
                        
                if not found and not is_standard_library(import_name):
                    unknown_packages.append(f"# {norm_name}  # Not found, might be a custom module")
        
        # Write known packages first
        for package in sorted(known_packages):
            f.write(f"{package}\n")
        
        # Then write unknown packages as comments
        if unknown_packages:
            f.write("\n# Modules not found in installed packages (may be custom code):\n")
            for package in sorted(unknown_packages):
                f.write(f"{package}\n")
                
    print(f"Requirements file generated at {output_file}")
    
    # Create a setup script for AWS
    with open('setup_aws.sh', 'w') as f:
        f.write("""#!/bin/bash
# Script to set up a fresh environment on AWS EC2

# Update package lists
sudo apt-get update

# Install Python and pip if not already installed
sudo apt-get install -y python3 python3-pip python3-venv

# Create and activate virtual environment
python3 -m venv venv
source venv/bin/activate

# Install requirements
pip install -r requirements.txt

# Print environment info
python3 -m pip list
python3 -V

echo "Environment setup complete!"
""")
    
    # Make the script executable
    os.chmod('setup_aws.sh', 0o755)
    print("AWS setup script generated at setup_aws.sh")

def main():
    print("===== Generating Comprehensive Requirements File =====")
    
    # Find all Python files
    directory = '.'
    py_files = find_all_py_files(directory)
    print(f"Found {len(py_files)} Python files")
    
    # Extract imports from all files
    all_imports = set()
    for file_path in py_files:
        imports = find_imports_in_file(file_path)
        all_imports.update(imports)
    
    # Remove standard library imports
    non_std_imports = {imp for imp in all_imports if not is_standard_library(imp)}
    print(f"Found {len(non_std_imports)} non-standard library imports")
    
    # Get installed packages
    installed_packages = get_installed_packages()
    print(f"Found {len(installed_packages)} installed packages")
    
    # Generate requirements file
    generate_requirements_file(non_std_imports, installed_packages)
    
    print("\nNext steps:")
    print("1. Copy requirements.txt and setup_aws.sh to your AWS EC2 instance")
    print("2. Run 'bash setup_aws.sh' on your AWS instance to set up the environment")
    print("3. Activate the virtual environment with 'source venv/bin/activate'")

if __name__ == "__main__":
    main()
import os
import shutil
from bs4 import BeautifulSoup
from php2py import PHPTranslator
from tkinter import Tk, filedialog
from djangify import convert_static_site
import subprocess

# Function to ask the user to select a folder
def select_directory():
    root = Tk()
    root.withdraw()  
    folder_path = filedialog.askdirectory(title="Select the folder with HTML, CSS, JS, and PHP files")
    return folder_path

# Function to convert HTML/CSS/JS to Django using Djangify
def convert_static_to_django(source_folder, project_name):
    try:
        print(f"Converting HTML, CSS, and JS files in {source_folder} to Django templates...")
        convert_static_site(source_folder, project_name)
        print("Static files converted successfully!")
    except ValueError as ve:
        print(f"Unsupported file type encountered: {ve}")
    except Exception as e:
        print(f"Error converting static files: {e}")

# Function to convert PHP to Python using php2py
def convert_php_to_python(source_folder, project_name):
    try:
        print(f"Converting PHP files in {source_folder} to Python...")

        for root, dirs, files in os.walk(source_folder):
            for file in files:
                if file.endswith(".php"):
                    php_file_path = os.path.join(root, file)
                    print(f"Converting {php_file_path}...")
                    with open(php_file_path, "r") as php_file:
                        php_code = php_file.read()
                    
                    # Translate PHP code to Python
                    python_code = PHPTranslator().from_php(php_code)

                    python_file_path = os.path.join(project_name, project_name, 'converted_php', file.replace(".php", ".py"))
                    os.makedirs(os.path.dirname(python_file_path), exist_ok=True)
                    with open(python_file_path, "w") as python_file:
                        python_file.write(python_code)
        
        print("PHP files converted successfully!")
    except Exception as e:
        print(f"Error converting PHP files: {e}")

# Function to create a Django project
def create_django_project(project_name):
    try:
        print(f"Creating Django project {project_name}...")
        subprocess.run(['django-admin', 'startproject', project_name], check=True)
        print(f"Django project {project_name} created successfully!")
    except FileNotFoundError as fnfe:
        print(f"Error: 'django-admin' command not found. Ensure Django is installed and available in your PATH. {fnfe}")
    except subprocess.CalledProcessError as e:
        print(f"Error creating Django project: {e}")
    except PermissionError as pe:
        print(f"Permission error while creating Django project: {pe}")

# Function to create necessary Django folders and install if not present
def setup_django_environment():
    try:
        # Check if Django is installed, and install it if not
        print("Checking if Django is installed...")
        subprocess.run(['pip', 'show', 'django'], check=True, stdout=subprocess.DEVNULL)
        print("Django is already installed.")
    except subprocess.CalledProcessError:
        print("Django is not installed. Installing Django...")
        subprocess.run(['pip', 'install', 'django'], check=True)
        print("Django installed successfully.")
    
    # Create folders for Django project
    try:
        print("Creating necessary folders...")
        if not os.path.exists('django_projects'):
            os.makedirs('django_projects')
        print("Folders created successfully!")
    except Exception as e:
        print(f"Error creating folders: {e}")

# Function to move static files (CSS, JS, images) to Django's static folder
def move_static_files(source_folder, project_name):
    static_folder = os.path.join(project_name, project_name, 'static')
    os.makedirs(static_folder, exist_ok=True)
    
    for root, dirs, files in os.walk(source_folder):
        for file in files:
            if file.endswith(('.css', '.js', '.png', '.jpg', '.jpeg', '.gif', '.svg')):
                static_file_path = os.path.join(root, file)
                dest_path = os.path.join(static_folder, os.path.relpath(static_file_path, source_folder))
                os.makedirs(os.path.dirname(dest_path), exist_ok=True)
                shutil.copy2(static_file_path, dest_path)

    print("Static files moved to Django's static folder successfully!")

# Function to move HTML files to Django templates folder
def move_html_files(source_folder, project_name):
    templates_folder = os.path.join(project_name, project_name, 'templates')
    os.makedirs(templates_folder, exist_ok=True)
    
    for root, dirs, files in os.walk(source_folder):
        for file in files:
            if file.endswith('.html'):
                html_file_path = os.path.join(root, file)
                dest_path = os.path.join(templates_folder, os.path.relpath(html_file_path, source_folder))
                os.makedirs(os.path.dirname(dest_path), exist_ok=True)
                shutil.copy2(html_file_path, dest_path)

    print("HTML files moved to Django's templates folder successfully!")

# Function to run Django server
def run_django_server(project_name):
    try:
        print("Starting Django development server...")
        subprocess.run(['python', os.path.join(project_name, 'manage.py'), 'runserver'], check=True)
    except subprocess.CalledProcessError as e:
        print(f"Error starting Django server: {e}")
    except Exception as e:
        print(f"Unexpected error: {e}")

def main():
    setup_django_environment()
    source_folder = select_directory()
    
    if not source_folder:
        print("No folder selected. Exiting...")
        return

    project_name = input("Enter the Django project name: ")

    create_django_project(project_name)
    convert_static_to_django(source_folder, project_name)
    move_static_files(source_folder, project_name)
    move_html_files(source_folder, project_name)
    convert_php_to_python(source_folder, project_name)

    print(f"Conversion process completed! Your Django project '{project_name}' is ready.")
    run_django_server(project_name)

if __name__ == "__main__":
    main()

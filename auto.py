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
                    

                    python_code = PHPTranslator().from_php(php_code)

                    python_file_path = os.path.join(project_name, 'converted_php', file.replace(".php", ".py"))
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
        subprocess.run(['django-admin', 'startproject', project_name])
        print(f"Django project {project_name} created successfully!")
    except Exception as e:
        print(f"Error creating Django project: {e}")

# Function to move static files (CSS, JS, images) to Django's static folder
def move_static_files(source_folder, project_name):
    static_folder = os.path.join(project_name, 'static')
    os.makedirs(static_folder, exist_ok=True)
    
    for root, dirs, files in os.walk(source_folder):
        for file in files:
            if file.endswith(('.css', '.js', '.png', '.jpg', '.jpeg', '.gif', '.svg')):
                static_file_path = os.path.join(root, file)
                dest_path = os.path.join(static_folder, os.path.relpath(static_file_path, source_folder))
                os.makedirs(os.path.dirname(dest_path), exist_ok=True)
                shutil.copy2(static_file_path, dest_path)

    print("Static files moved to Django's static folder successfully!")


def main():

    source_folder = select_directory()
    
    if not source_folder:
        print("No folder selected. Exiting...")
        return

    project_name = input("Enter the Django project name: ")


    create_django_project(project_name)


    convert_static_to_django(source_folder, project_name)


    move_static_files(source_folder, project_name)


    convert_php_to_python(source_folder, project_name)

    print(f"Conversion process completed! Your Django project '{project_name}' is ready.")

if __name__ == "__main__":
    main()

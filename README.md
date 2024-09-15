# Djangify

# Automating Old Webpage Conversion to Django 🛠️

## Why I Created This

So here's the deal: one of my developer friends hit me up with this problem. They had a bunch of old websites written in **PHP** and good old **HTML/CSS/JS**, and they wanted to give them a fresh start using Django. 🤯 I thought, "Why not make this process easier for everyone?" After all, devs often work with legacy tech, and sometimes you just need to upgrade without starting from scratch.

That’s where this Python script comes in! It automates the conversion of HTML/CSS/JS/PHP files into a clean Django project—no need to manually rework everything from the ground up. ⚡️

## What This Does 🧰

- Converts **HTML** templates into Django's templating system.
- Moves **CSS/JS** into Django’s static folder.
- **Converts PHP** scripts into Python using `php2py`, so you can start working with Django views and models in no time.
- Sets up a fresh **Django project** in a click.
- **Static files**? No worries, the script handles those too.

## How To Get This Working 🚀

### Step 1: Install the Requirements

Make sure you have the following Python packages installed:

```bash
pip install djangify php2py beautifulsoup4 lxml django
```

### Step 2: Download the Python Script

Get the Python script (I call it `auto.py`), and make sure it's in a place where you can run it (like your project folder or Desktop).

### Step 3: Run the Script

Open up your terminal (or command prompt) and run:

```bash
auto.py
```

### Step 4: Select the Folder with Your Old Web Files 🗂️

The script will ask you to select the folder where your **HTML/CSS/JS/PHP** files are. Just navigate to that folder and select it. The script will take care of the rest.

### Step 5: Name Your Django Project 🎉

It will ask for a name for your new Django project. Choose a cool name, and boom—you've got a Django project with all your old files integrated.

## API Additions

If you want to add **APIs**, you can easily extend the Django project:
- Use **Django REST Framework** to create APIs. Install it via `pip install djangorestframework`.
- Add API views in `views.py`, serializers in `serializers.py`, and configure routes in `urls.py`.

For example, add this to your `views.py` to expose a simple API:

```python
from rest_framework.views import APIView
from rest_framework.response import Response

class SimpleAPI(APIView):
    def get(self, request):
        data = {"message": "Hello from your API!"}
        return Response(data)
```

### Adding the URL to Your API:
In `urls.py`:

```python
from django.urls import path
from .views import SimpleAPI

urlpatterns = [
    path('api/simple/', SimpleAPI.as_view(), name='simple-api'),
]
```

## Need Help? 🤔

If you run into any issues or have questions, feel free to hit me up! 📨 I’m here to help you sort out any bumps in the road. 

Enjoy your freshly upgraded Django project! 🎉✨

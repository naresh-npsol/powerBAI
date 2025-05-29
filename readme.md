# Smartshorts: AI Video Generation and Distribution Platform

Smartshorts is a cutting-edge Django-based platform designed to create AI-driven videos and distribute them across social media platforms like YouTube, TikTok, and Instagram. Built upon the Django SaaS boilerplate, this project incorporates several advanced features and customizations to supercharge video creation and delivery.

---

## Why Smartshorts?

With Smartshorts, users can:

- Harness AI to create dynamic, engaging videos effortlessly.
- Automate video uploads to platforms like YouTube, TikTok, and Instagram.
- Save time and focus on content strategy rather than repetitive tasks.

**#AIContentCreationSimplified**

---

## Features

### AI Video Creation
- **AI-driven script generation**
- **Voiceover synthesis**
- **Automatic video editing and effects**

### Distribution
- Direct API integration for uploading to:
  - YouTube
  - TikTok
  - Instagram

### Additional Custom Features
- **Channels App:** Organize content by categories and channels.
- **Shorts App:** Manage short-form video content optimized for social platforms.

### SaaS Features (Inherited from Boilerplate)
- User authentication (custom user model with login/signup flows)
- Subscription management with Stripe integration
- Blog and content management with WYSIWYG editor
- Responsive landing and pricing pages
- Dynamic sitemap and technical SEO optimization

---

## Installation and Setup

Follow the steps below to set up the Smartshorts project locally:

### Requirements
- Python 3.10+
- PostgreSQL
- Node.js (for Tailwind CSS and other frontend dependencies)

### Steps
1. Clone the repository:
    ```bash
    git clone <repository_url>
    ```

2. Navigate to the project directory:
    ```bash
    cd smartshorts
    ```

3. Set up a Python virtual environment (optional but recommended):
    ```bash
    python -m venv venv
    source venv/bin/activate  # On Windows: venv\Scripts\activate
    ```

4. Install Python dependencies:
    ```bash
    pip install -r requirements.txt
    ```

5. Set up the `.env` file in the `project` folder with the following variables:
    ```env
    DEBUG=1
    PYTHON_VERSION=3.10
    DOMAIN=""

    ALLOWED_HOSTS=".up.railway.app"
    SECRET_KEY="<your_secret_key>"

    POSTGRES_DATABASE="<database_name>"
    POSTGRES_USER="<database_user>"
    POSTGRES_PASSWORD="<database_password>"
    POSTGRES_HOST="<database_host>"

    STRIPE_TEST_API_KEY="<your_test_key>"
    STRIPE_PROD_API_KEY="<your_prod_key>"

    GOOGLE_ANALYTICS="G-<your_tracking_id>"
    ```

6. Apply migrations to set up the database:
    ```bash
    python manage.py migrate
    ```

7. Create a superuser:
    ```bash
    python manage.py createsuperuser
    ```

8. Start the development server:
    ```bash
    python manage.py runserver
    ```
    Access the site at [http://localhost:8000](http://localhost:8000).

9. Start Tailwind CSS for frontend development:
    ```bash
    python manage.py tailwind start
    ```

---

## Deployment

### Production Setup
- Deploy to platforms like Vercel, Railway, or Render.
- Run the following command to collect static files:
    ```bash
    python manage.py collectstatic
    ```
- Set `DEBUG=0` in the `.env` file for production.
- Generate a new secret key using the following command in a Python shell:
    ```python
    from django.core.management.utils import get_random_secret_key
    get_random_secret_key()
    ```

### Firebase for Storage
- Configure Firebase for persistent storage.
- Convert the Firebase credentials file to base64 for deployment:
    ```bash
    base64 firebase-cred.json > encoded.txt
    ```
- Add the encoded credentials to the `.env` file as `FIREBASE_ENCODED`.

---

## Usage

### AI Video Workflow
1. Upload or generate a script using the AI assistant.
2. Customize the script and voiceover settings.
3. Generate the video with built-in templates and effects.

### Video Distribution
1. Link social media accounts through the admin panel.
2. Schedule or directly upload videos to YouTube, TikTok, and Instagram.
3. Monitor analytics and performance from the dashboard.

---

## Tutorials and Resources

### AI Features
- Learn how to use AI for script and video generation.

### API Integrations
- Detailed guides for connecting social media APIs for seamless uploads.

### Payment Integration
- Manage subscriptions with Stripe.

---

## Contribute


### Report Issues
- Open an issue on GitHub to report bugs or suggest features.

---

Smartshorts is your go-to solution for automated AI video creation and distribution. Build engaging content faster and smarter!


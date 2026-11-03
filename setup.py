from setuptools import find_packages, setup

setup(
    name="sla-ticket-routing",
    version="0.1.0",
    description="AI-powered SLA breach prediction and ticket routing for JIRA.",
    author="Basani Ganesh",
    author_email="",
    packages=find_packages(include=["src", "src.*"]),
    install_requires=[
        "flask==3.0.3",
        "gunicorn==21.2.0",
        "joblib==1.5.2",
        "pandas==2.3.3",
        "python-dotenv==1.2.1",
        "scikit-learn==1.7.2",
    ],
    python_requires=">=3.10",
    include_package_data=True,
)


# Use a the pytorch image provided by jetson-containers
FROM dustynv/l4t-pytorch:r36.2.0

# Set environment variables for Poetry and Python
ENV POETRY_VERSION=1.7.1 \
    POETRY_HOME="/opt/poetry" \
    POETRY_VIRTUALENVS_IN_PROJECT=true \
    POETRY_NO_INTERACTION=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=off \
	DEBIAN_FRONTEND=noninteractive

# Add Poetry to the PATH
ENV PATH="$POETRY_HOME/bin:$PATH"

# Install system dependencies required for your project and Poetry installation
# Includes curl for installing Poetry and python3/pip if not fully present
# Also includes potentially needed build tools for some Python packages (like those with C extensions)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    python3.9 python3.9-venv python3-pip \
	libgl1 \
	libglib2.0-0 \
    libsm6 \
    libxrender1 \
    libxext6 \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Ensure python3.9 is the default python
RUN update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.9 1 \
    && update-alternatives --install /usr/bin/python python /usr/bin/python3.9 1

# Install Poetry
RUN curl -sSL https://install.python-poetry.org | python3 -

WORKDIR /app

# Copy only the essential files for dependency installation
COPY . .

# Install project dependencies (excluding dev, lint, tests, docs groups)
RUN poetry install

# Add the virtual environment's bin directory to the PATH
ENV VIRTUAL_ENV=/app/.venv
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

WORKDIR /app

# Set the entrypoint to the python executable within the virtual environment
#ENTRYPOINT ["python"]

# Default command if no script is specified (optional)
#CMD ["scripts/main.py"]
FROM mambaorg/micromamba:1.5.10

# Here you can point to the source repository of this Dockerfile:
LABEL org.opencontainers.image.source="https://github.com/eWaterCycle/pcrglobwb-bmi"

LABEL maintainer="Andre van der Veen <A.B.vanderVeen-1@student.tudelft.nl>" 
LABEL version="0.2.3"

# Copy the environment.yml first
COPY environment.yml /tmp/environment.yml

# Create the environment from YAML
RUN micromamba create -f /tmp/environment.yml -y \
    && micromamba clean --all --yes

# Activate the environment by default
ARG MAMBA_DOCKERFILE_ACTIVATE=1
ENV PATH=/opt/conda/envs/pcrglobwb_python3/bin:$PATH
ENV CONDA_DEFAULT_ENV=pcrglobwb_python3

# Install C/C++ compilers required to build Cython extensions 
USER root

RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc g++ \
    && rm -rf /var/lib/apt/lists/*

# Return to the default non-root user
USER $MAMBA_USER

# Copy project code
COPY . /usr/src/app
WORKDIR /usr/src/app



# Install your package (if needed)
RUN pip install .


WORKDIR /usr/src/app/model

USER root

# Compile imagemean.pyx
RUN cythonize -i imagemean.pyx


# Make project importable
ENV PYTHONPATH=/usr/src/app:/usr/src/app/model

WORKDIR /usr/src/app


# Entry point
ENTRYPOINT ["run-bmi-server", "--path", "/usr/src/app", "--name", "model.bmiPcrglobwb.BmiPCRGlobWB", "--port", "55555", "--debug"]












# FROM mambaorg/micromamba:1.3.1

# LABEL maintainer="Andre van der Veen <A.B.vanderVeen-1@student.tudelft.nl>" 
# LABEL version="0.1"

# # Copy the environment.yml first
# COPY environment.yml /tmp/environment.yml

# # Create the environment from YAML
# RUN micromamba create -f /tmp/environment.yml -y \
#     && micromamba clean --all --yes

# # Activate the environment by default
# ARG MAMBA_DOCKERFILE_ACTIVATE=1
# ENV PATH=/opt/conda/envs/pcrglobwb_python3/bin:$PATH
# ENV CONDA_DEFAULT_ENV=pcrglobwb_python3

# # Copy pyproject.toml and the model folder

# COPY model /usr/src/app/
# WORKDIR /usr/src/app

# # Install the model package and compile .pyx files
# #RUN micromamba run -n pcrglobwb_python3 pip install .
# RUN pip install .
# # Ensure grpc4bmi is installed (can also include in environment.yml pip section)
# #RUN pip install grpc4bmi==0.4.0

# # Make project importable
# ENV PYTHONPATH=/usr/src/app:/usr/src/app/model

# # Entry point
# ENTRYPOINT ["run-bmi-server", "--path", "/usr/src/app", "--name", "model.bmiPcrglobwb.BmiPCRGlobWB", "--port", "55555", "--debug"]

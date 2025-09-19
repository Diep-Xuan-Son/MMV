**<h1>Make Marketing Video</h1>**

## Installation
```bash
git clone http://git.mqsolutions.vn:8083/MQ-AI/MMV.git
cd MMV
pip install -r requirement.txt
pip install -r requirements_serving.txt
pip install -r requirements_ui.txt
```

## Usage
```bash
cd src
python controller.py
python test/test_ui.py
```

## Deployment

```bash
cd docker
# Change information of services in .env file and run command below:
docker-compose -f docker-compose.yml --profile "*" up -d
```

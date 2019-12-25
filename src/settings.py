import pathlib
import platform
import yaml

BASE_DIR = pathlib.Path(__file__).parent
PRO_DIR = BASE_DIR.parent
config_path = BASE_DIR / 'config.yaml'


def get_config(path):
    res = {
        "mysql": {},
        "redis": {},
        "jwt-secret": "",
    }
    with open(path) as rf:
        tmp = yaml.load(rf, Loader=yaml.FullLoader)
        res["jwt-secret"] = tmp["jwt-secret"]
        if platform.system() == 'Darwin':
            res["mysql"] = tmp["local-mysql"]
            res["redis"] = tmp["local-redis"]
        else:
            res["mysql"] = tmp["pro-mysql"]
            res["redis"] = tmp["pro-redis"]
    return res


config = get_config(config_path)

if __name__ == '__main__':
    print(config)
    print(BASE_DIR.parent)

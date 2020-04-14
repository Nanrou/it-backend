import pathlib
import platform
import yaml
import os

BASE_DIR = pathlib.Path(__file__).parent
PRO_DIR = BASE_DIR.parent
config_path = BASE_DIR / 'config.yaml'
DOWNLOAD_DIR = BASE_DIR / 'download'


def get_config(path):
    if not os.path.exists(DOWNLOAD_DIR):
        os.mkdir(DOWNLOAD_DIR)
    res = {
        "mysql": {},
        "redis": {},
        "jwt-secret": "",
        "smtp": {},
        "sms": {},
        "wechat": {}
    }
    with open(path) as rf:
        tmp = yaml.load(rf, Loader=yaml.FullLoader)
        res["jwt-secret"] = tmp["jwt-secret"]
        res["smtp"] = tmp["smtp"]
        res["sms"] = tmp["sms"]
        res["wechat"] = tmp["wechat"]
        if platform.system() == 'Darwin':
            res["mysql"] = tmp["local-mysql"]
            res["redis"] = tmp["local-redis"]
        else:
            res["mysql"] = tmp["pro-mysql"]
            res["redis"] = tmp["pro-redis"]
        # res["redis"] = tmp["local-redis"]
    return res


CONFIG = get_config(config_path)

if __name__ == '__main__':
    print(CONFIG)
    print(BASE_DIR.parent)

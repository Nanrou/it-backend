class ErrcodeABC:
    errcode = -1
    errmsg = ''

    def __init__(self, data: [dict, list] = None):
        if data is None:
            self.data = {}
        else:
            self.data = data

    def json(self):
        return {
            "errcode": self.errcode,
            "errmsg": self.errmsg,
            "data": self.data
        }

    @classmethod
    def json_without_data(cls):
        return {
            "errcode": cls.errcode,
            "errmsg": cls.errmsg,
        }


class ResponseOk(ErrcodeABC):
    errcode = 0


class InvalidTokenResponse(ErrcodeABC):
    errcode = 100001
    errmsg = '登录过期，请重新登录'


class RepetitionLoginResponse(ErrcodeABC):
    errcode = 100002
    errmsg = '此账号已在其他地方登录！'


class InvalidUserDataResponse(ErrcodeABC):
    errcode = 100003
    errmsg = '账号或密码错误'


class InvalidOriginPasswordResponse(ErrcodeABC):
    errcode = 100004
    errmsg = '原密码错误'


class RepetitionUserResponse(ErrcodeABC):
    errcode = 100005
    errmsg = '该用户已存在'


class MissRequiredFields(ErrcodeABC):
    errcode = 100005
    errmsg = '缺失必要参数'

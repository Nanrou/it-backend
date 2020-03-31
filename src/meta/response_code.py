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


class MissRequiredFieldsResponse(ErrcodeABC):
    errcode = 100005
    errmsg = '缺失必要参数'


class MissComputerHardwareResponse(ErrcodeABC):
    errcode = 100006
    errmsg = '该电脑无相关硬件信息'


class InvalidFormFIELDSResponse(ErrcodeABC):
    errcode = 100007
    errmsg = '表单字段错误'


class RepetitionHardwareResponse(ErrcodeABC):
    errcode = 100008
    errmsg = '该硬件信息已存在'


class InvalidCaptchaResponse(ErrcodeABC):
    errcode = 100009
    errmsg = '验证码错误'


class ConflictStatusResponse(ErrcodeABC):
    errcode = 100010
    errmsg = '请检查设备状态'


class RepetitionOrderIdResponse(ErrcodeABC):
    errcode = 1000011
    errmsg = 'OrderId重复，请稍后尝试'


class InvalidWorkerInformationResponse(ErrcodeABC):
    errcode = 100012
    errmsg = '预留身份信息错误'


class EmtpyPatrolPlanResponse(ErrcodeABC):
    errcode = 100013
    errmsg = '该设备无巡检计划'


class OrderMissContentResponse(ErrcodeABC):
    errcode = 100014
    errmsg = '该流程缺失记录，请联系管理员'


class SendEmailTimeoutResponse(ErrcodeABC):
    errcode = 100015
    errmsg = '发送邮件失败，请稍后重试'


class DispatchSuccessWithoutSendEmailResponse(ErrcodeABC):
    errcode = 100016
    errmsg = '指派成功，但发送邮件失败，请手动重发'


class MissEmailContentResponse(ErrcodeABC):
    errcode = 100017
    errmsg = '无邮件发送记录'


class AlreadySendEmailResponse(ErrcodeABC):
    errcode = 100018
    errmsg = '已发送邮件通知'


class SmsLimitResponse(ErrcodeABC):
    errcode = 100019
    errmsg = '发送短信过于频繁，请稍后尝试'


class SendSmsErrorResponse(ErrcodeABC):
    errcode = 100020
    errmsg = '短信发送失败'


class PrivacyWarningResponse(ErrcodeABC):
    errcode = 100021
    errmsg = '本系统为内部系统，请联系管理员绑定企业微信'


class NeedBindingResponse(ErrcodeABC):
    errcode = 100022
    errmsg = '需执行绑定操作'


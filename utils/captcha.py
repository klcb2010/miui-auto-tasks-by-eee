'''
Date: 2023-11-13 19:55:22
LastEditors: Night-stars-1 nujj1042633805@gmail.com
LastEditTime: 2023-12-18 20:46:51
'''
import asyncio
import json
from twocaptcha import TwoCaptcha

from .request import post
from .logger import log
from .config import ConfigManager
from .data_model import ApiResultHandler, GeetestResult

_conf = ConfigManager.data_obj

def find_key(data: dict, key: str):
    """递归查找字典中的key"""
    for dkey, dvalue in data.items():
        if dkey == key:
            return dvalue
        if isinstance(dvalue, dict):
            find_key(dvalue, key)
    return None

async def get_validate_by_eee(gt: str, challenge: str) -> GeetestResult:  # pylint: disable=invalid-name
    """获取人机验证结果"""
    try:
        validate = None
        if _conf.preference.geetest_url:
            params = _conf.preference.geetest_params.copy()
            params = json.loads(json.dumps(params).replace("{gt}", gt).replace("{challenge}", challenge))
            data = _conf.preference.geetest_data.copy()
            data = json.loads(json.dumps(data).replace("{gt}", gt).replace("{challenge}", challenge))
            response = await post(
                _conf.preference.geetest_url,
                params=params,
                json=data,
            )
            log.debug(response.text)
            geetest_data = response.json()
            geetest = ApiResultHandler(geetest_data)
            challenge = find_key(geetest.data, "challenge")
            validate = find_key(geetest.data, "validate")
            return GeetestResult(challenge=challenge, validate=validate)
        else:
            return GeetestResult(challenge="", validate="")
    except Exception:  # pylint: disable=broad-exception-caught
        log.exception("获取人机验证结果异常")
        return GeetestResult(challenge="", validate="")
async def get_validate_by_2captcha(gt: str, challenge: str, websiteUrl: str) -> GeetestResult:  # pylint: disable=invalid-name
    """获取人机验证结果(2captcha)"""
    try:
        try:
            solver = TwoCaptcha(_conf.preference.twocaptcha_api_key)
            geetest_data = solver.geetest(gt=gt,challenge=challenge,url=websiteUrl,userAgent=_conf.preference.twocaptcha_userAgent)
        except Exception as twocaptcha_exception:
            log.error(f"2captcha异常: {twocaptcha_exception}")
            return GeetestResult(challenge="", validate="", taskId="")
        captchaId=geetest_data["captchaId"]
        geetest = json.loads(geetest_data["code"])
        challenge = geetest["geetest_challenge"]
        validate = geetest["geetest_validate"]
        log.info("已拿到2captcha返回的challenge和validate")
        return GeetestResult(challenge=challenge, validate=validate, taskId=captchaId)
    except Exception:  # pylint: disable=broad-exception-caught
        log.exception("获取人机验证结果异常")
        return GeetestResult(challenge="", validate="",taskId="")
   
async def get_validate_by_ttocr(gt: str, challenge: str, websiteUrl: str) -> GeetestResult:  # pylint: disable=invalid-name
    """获取人机验证结果(ttocr)"""
    try:
        createTask_url = _conf.preference.ttocr.createTask_url
        validate = ""
        createTask_data = _conf.preference.ttocr.createTask_data.copy()
        createTask_data["appkey"] = _conf.preference.ttocr.app_key
        createTask_data["gt"] = gt
        createTask_data["challenge"] = challenge
        createTask_data["referer"] = websiteUrl
        for key, value in createTask_data.items():
            if isinstance(value, str):
                createTask_data[key] = value.format(gt=gt, challenge=challenge)
        log.debug("post "+ str(createTask_data) + " to " + str(createTask_url))
        response1 = await post(
            createTask_url,
            data=createTask_data,
        )
        result1 = response1.json()
        if result1["status"] == 1:
            resultid = result1["resultid"]
            log.info("ttocr创建任务成功，resultId："+str(resultid))
        else:
            log.error("ttocr创建任务接口返回错误：" + response1.text)
            return GeetestResult(challenge="", validate="")
        
        # 等待一段时间，具体时间根据文档来调整
        log.info("等待10秒后向ttocr查询结果")
        await asyncio.sleep(10)  

        # 处理ttocr获取结果接口的数据
        getTaskResult_url = _conf.preference.ttocr.getTaskResult_url
        getTaskResult_data = {}
        getTaskResult_data["appkey"] = _conf.preference.ttocr.app_key
        getTaskResult_data["resultid"] = resultid

        # 发送到ttocr获取结果接口的请求
        for _ in range(30):
            response2 = await post(
                getTaskResult_url,
                json=getTaskResult_data,
            )
            geetest_data = response2.json() 
            geetest = ApiResultHandler(geetest_data)
            if geetest.success:
                challenge = geetest.data["challenge"]
                validate = geetest.data["validate"]
                log.info("已拿到ttocr返回的challenge和validate")
                return GeetestResult(challenge=challenge, validate=validate)
            elif geetest.message == "等待识别结果" and geetest.status == 2 :
                log.info("人机验证结果尚未准备好，等待10秒后重试")
                await asyncio.sleep(10)  # 先等个2秒
            elif geetest.status == 4016 and geetest.message == "结果不存在":
                log.error("ttocr获取结果接口返回错误：" + response2.text)
                break
            else:
                log.error("ttocr获取结果接口返回错误：" + response2.text + "，可能是还没解决，等十秒再试一次")
        return GeetestResult(challenge="", validate="")
    except Exception: # pylint: disable=broad-exception-caught
        log.exception("获取人机验证结果异常")
        return GeetestResult(challenge="", validate="")

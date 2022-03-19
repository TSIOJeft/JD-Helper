import random
import sys
import time
import requests
import json
from utils import log, config, parse_json, session, get_sku_title, send_wechat, ntp_sync, Timer
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime


class JDHelper(object):
    def __init__(self):
        self.config = config
        self.session = session()
        self.purchase_num = 1
        self.sku_id = self.config.get_config('config', 'sku_id')
        self.order_data = dict()
        self.init_info = dict()
        self.timers = Timer()
        self.buy_time = datetime.strptime(
            config.get_config('config', 'buy_time'), "%Y-%m-%d %H:%M:%S.%f")
        log.info('正在同步系统时间')
        # self.timers.time_sync()

    # DESCRIPTION: 调用多个进程异步执行抢购程序
    # INPUT:
    #   work_count: 异步程序个数
    # OUTPUT:
    # AUTHOR:2021.03.13
    def pool_executor(self, work_count=1):
        with ProcessPoolExecutor(work_count) as pool:
            for i in range(work_count):
                pool.submit(self.flash_sale)

    # DESCRIPTION: 获取用户购物车，用以验证登录是否成功
    # INPUT:    None
    # OUTPUT:   None
    # Author:   XuKaikai@2021.03.12
    def login(self):
        for flag in range(1, 3):
            try:
                targetURL = 'https://order.jd.com/center/list.action'
                payload = {
                    'rid': str(int(time.time() * 1000)),
                }
                resp = self.session.get(url=targetURL,
                                        params=payload,
                                        allow_redirects=False)
                if resp.status_code == requests.codes.OK:
                    log.info('校验是否登录[成功]')
                    log.info('用户:{}'.format(self.get_username()))
                    return True
                else:
                    log.info('校验是否登录[失败]')
                    log.info('请重新输入cookie')
                    time.sleep(1)
                    continue
            except Exception as e:
                log.error(e)
                log.info('第【%s】次失败请重新获取cookie', flag)
                time.sleep(1)
                continue
        sys.exit(1)

    # DESCRIPTION: 预约抢购
    # INPUT:    None
    # OUTPUT:   None
    # AUTHOR:   XuKaikai@2021.03.13
    def reserve(self):
        self.login()
        log.info('登录成功')
        buy_time_ms = int(
            time.mktime(self.buy_time.timetuple()) * 1000.0 +
            self.buy_time.microsecond / 1000)
        url = 'https://yushou.jd.com/youshouinfo.action?'
        payload = {
            'callback': 'fetchJSON',
            'sku': self.sku_id,
            '_': str(int(time.time() * 1000)),
        }
        headers = {
            'Referer': 'https://item.jd.com/{}.html'.format(self.sku_id),
        }

        log.info('正在进行预约')
        rsp = self.session.get(url=url, params=payload, headers=headers)
        log.debug(rsp.text)
        rsp_json = parse_json(rsp.text)
        reserve_url = rsp_json.get('url')
        self.timers.start()
        while True:
            try:
                self.session.get(url='https:' + reserve_url)
                log.info('预约成功，已获得抢购资格 / 您已成功预约过了，无需重复预约')
                if config.get_config('messenger', 'enable') == 'true':
                    success_message = "预约成功，已获得抢购资格 / 您已成功预约过了，无需重复预约"
                    send_wechat(success_message)
                break
            except Exception as e:
                log.error('预约失败正在重试...')

    # DESCRIPTION: 通过向服务器发送特定报文用以验证登录是否成功
    # INPUT:    None
    # OUTPUT:   cookies文件对应的用户名
    # Author:   XuKaikai@2021.03.12
    def get_username(self):
        url = 'https://passport.jd.com/user/petName/getUserInfoForMiniJd.action'
        payload = {
            'callback': 'jQuery'.format(random.randint(1000000, 9999999)),
            '_': str(int(time.time() * 1000)),
        }

        headers = {'Referer': 'https://order.jd.com/center/list.action'}

        rsp = self.session.get(url=url, params=payload, headers=headers)
        try_count = 5
        while not rsp.text.startswith('jQuery'):
            try_count = try_count - 1
            if try_count > 0:
                rsp = self.session.get(url=url,
                                       params=payload,
                                       headers=headers)
            else:
                break

        return parse_json(rsp.text).get('nickName')

    # DESCRIPTION:抢购程序
    # INPUT:    None
    # OUTPU:    抢购结果
    # AUTHOR:   2021.03.13
    def flash_sale(self):
        self.login()
        log.info('登录成功')
        # for i in range(3):
        self.timers.start()
        self.get_seckill_url()
        self.toCart()
        self.checkcartall()
        self.checkout()
        self.submit_order()
        # 尝试3次 300ms
        # time.sleep(1)
        # self.checkout()
        # self.submit_order()
        # while True:
        #     try:
        #         if not (self.checkout()):
        #             continue
        #         if not (self.submit_order()):
        #             continue
        #         else:
        #             sys.exit(0)
        #     except Exception as e:
        #         log.info('抢购发生异常，稍后继续执行:', e)
        #     time.sleep(random.randint(10, 100) / 1000)

        # DESCRIPTION:添加抢购商品到购物车，然后抢购开始后直接进结算页面
        # INPUT:    None
        # OUTPUT:   None
        # AUTHOR:   XuKaikai@2021.03.13

    def toCart(self):
        log.info('正在访问商品的抢购连接......')
        url = 'https://cart.jd.com/gate.action'
        payload = {
            'pcount': self.purchase_num,
            'ptype': '1',
            'pid': self.sku_id
        }
        headers = {
            'Host': 'cart.jd.com',
            'Referer': 'https://item.jd.com/{}.html'.format(self.sku_id),
        }
        rsp = self.session.get(url=url, params=payload, headers=headers)
        if rsp.status_code == requests.codes.OK:
            log.info('成功加入购物')
        else:
            log.error("失败：" + rsp.text)
            log.error('添加购物车失败，状态码：' + str(rsp.status_code))
        return True

    # DESCRIPTION: 访问抢购订单结算页面
    # INPUT:    None
    # OUTPUT:   None
    # AUTHOR:   XuKaikai@2021.03.13
    def checkout(self):
        url = 'https://trade.jd.com/shopping/order/getOrderInfo.action'
        headers = {
            'Host': 'trade.jd.com',
            'Referer': 'https://cart.jd.com/cart_index/',
        }

        rsp = self.session.get(url=url, headers=headers)
        if rsp.status_code == requests.codes.OK:
            log.info('去结算')
            return True
        else:
            log.error('访问订单结算页面失败，状态码：' + str(rsp.status_code) + ' 正在重试...')
            return False

    # DESCRIPTION: 提交抢购订单
    # INPUT：   None
    # OUTPUT:   抢购结果
    # AUTHOR:   XuKaikai@03.13
    def submit_order(self):
        url = 'https://trade.jd.com/shopping/order/submitOrder.action?='
        payload = {'presaleStockSign': '1'}
        headers = {
            'authority': 'trade.jd.com',
            'method': 'POST',
            'path': '/ shopping / order / submitOrder.action? & presaleStockSign = 1',
            'scheme': 'https',
            'Host': 'trade.jd.com',
            'Referer': 'https://trade.jd.com/shopping/order/getOrderInfo.action',
            'origin': 'https: // trade.jd.com',
            'accept': 'application / json, text / javascript, * / *; q = 0.01',
            'accept - encoding': 'gzip, deflate, br',
            'accept - language': 'zh - CN, zh;q = 0.9',
            'content - length': '390',
            'content - type': 'application / x - www - form - urlencoded',
            'sec - ch - ua': '" Not A;Brand";v = "99", "Chromium";v = "99", "Google Chrome"; v = "99" ',
            'sec - ch - ua - mobile': '?0',
            'sec - ch - ua - platform': '"Windows"',
            'sec - fetch - dest': 'empty',
            'sec - fetch - mode': 'cors',
            'sec - fetch - site': 'same - origin',
            'user - agent': 'Mozilla / 5.0(Windows NT 10.0;Win64;x64) AppleWebKit / 537.36(KHTML, like Gecko) Chrome / 99.0.4844.51 Safari / 537.36',
            'x - requested - with': 'XMLHttpRequest'
        }
        rsp = self.session.post(url=url, params=payload, headers=headers)
        if rsp.status_code == requests.codes.OK:
            log.info('正在提交订单...')
        else:
            log.error('订单提交失败，状态码：' + str(rsp.status_code) + ' 正在重试...')
        try:
            rsp_json = json.loads(rsp.text)
        except Exception as e:
            # log.error(e)
            log.error('提交订单失败，请稍后重试')
            return False
        if rsp_json.get('success'):
            order_id = rsp_json.get('orderId')
            log.info('抢购成功，订单号:{},'.format(order_id))
            if config.get_config('messenger', 'enable') == 'true':
                success_message = "抢购成功，订单号:{}, 请尽快到PC端进行付款".format(order_id)
                send_wechat(success_message)
            return True
        else:
            log.info('抢购失败，返回信息:{}'.format(rsp_json))
            return False

    def get_seckill_url(self):
        """获取商品的抢购链接
        点击"抢购"按钮后，会有两次302跳转，最后到达订单结算页面
        这里返回第一次跳转后的页面url，作为商品的抢购链接
        :return: 商品的抢购链接
        """
        url = 'https://itemko.jd.com/itemShowBtn'
        payload = {
            'callback': 'jQuery{}'.format(random.randint(1000000, 9999999)),
            'skuId': self.sku_id,
            'from': 'pc',
            '_': str(int(time.time() * 1000)),
        }
        headers = {
            'Host': 'itemko.jd.com',
            'Referer': 'https://item.jd.com/',
            'Accept': '* / *',
            'Accept - Encoding': 'gzip, deflate, br',
            'Accept - Language': 'zh - CN, zh;q = 0.9',
            'Connection': 'keep - alive',
            'sec - ch - ua': '" Not A;Brand";v = "99", "Chromium";v = "99", "Google Chrome"; v = "99" ',
            'sec - ch - ua - mobile': '?0',
            'sec - ch - ua - platform': '"Windows"',
            'sec - fetch - dest': 'empty',
            'sec - fetch - mode': 'cors',
            'sec - fetch - site': 'same - origin',
            'user - agent': 'Mozilla / 5.0(Windows NT 10.0;Win64;x64) AppleWebKit / 537.36(KHTML, like Gecko) Chrome / 99.0.4844.51 Safari / 537.36'
        }

        resp = self.session.get(url=url, headers=headers, params=payload)
        log.info(resp.text)
        resp_json = parse_json(resp.text)
        if resp_json.get('url'):
            # https://divide.jd.com/user_routing?skuId=8654289&sn=c3f4ececd8461f0e4d7267e96a91e0e0&from=pc
            router_url = 'https:' + resp_json.get('url')
            # https://marathon.jd.com/captcha.html?skuId=8654289&sn=c3f4ececd8461f0e4d7267e96a91e0e0&from=pc
            seckill_url = router_url.replace(
                'divide', 'marathon').replace(
                'user_routing', 'captcha.html')
            log.info("抢购链接获取成功: %s", seckill_url)
            self.request_seckill_checkout_page()
            return seckill_url
        else:
            log.info("抢购链接获取失败，稍后自动重试")

    def request_seckill_checkout_page(self):

        """访问抢购订单结算页面"""
        log.info('[结算页面] 访问抢购订单结算页面...')
        url = 'https://marathon.jd.com/seckillnew/orderService/pc/submitOrder.action'
        payload = {
            'skuId': self.sku_id,
            'num': 1,
            'rid': int(time.time())
        }
        headers = {
            'user - agent': 'Mozilla / 5.0(Windows NT 10.0;Win64;x64) AppleWebKit / 537.36(KHTML, like Gecko) Chrome / 99.0.4844.51 Safari / 537.36',
            'Host': 'marathon.jd.com',
            'Referer': 'https://marathon.jd.com/seckill/seckill.action?skuId={}&num=1'.format(self.sku_id),
        }
        resp = self.session.get(url=url, params=payload, headers=headers, allow_redirects=False)
        log.info(resp.text)
        return

    def checkcartall(self):

        url = 'https://api.m.jd.com/api'
        payload = {
            'functionId': 'pcCart_jc_cartCheckAll',
            'appid': 'JDC_mall_cart',
            'loginType': 3,
            'body': '{"serInfo":{"area":"3_51045_55801_0","user-key":" "}}'
        }
        headers = {
            'authority': 'api.m.jd.com',
            'method': 'POST',
            'scheme': 'https',
            'Referer': 'https://cart.jd.com',
            'origin': 'https://cart.jd.com/',
        }
        rsp = self.session.post(url=url, params=payload, headers=headers)
        rsp_json = json.loads(rsp.text)
        if rsp_json.get('success'):
            log.info("全选购物车: 成功")
        else:
            log.info("全选购物车: 失败")

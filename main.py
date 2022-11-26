import os
import re
import urllib
from threading import Lock
from platform import system
from threading import Thread
from multiprocessing import Queue
from http.client import HTTPResponse
from urllib.request import Request, urlopen


# PathSeparator: 路径分隔符
PathSeparator: str = '\\' if system() == 'Windows' else '/'

FileCount: int = 1          # 文件名计数
FileLock: Lock = Lock()     # 文件名锁 (用于保证文件名的有序生成)


def mkdir(_path: str) -> None:
    """
    判断路径 _Path 是否存在, 不存在则逐级创建, 存在则什么也不做
    """
    _path = _path.strip()

    path_temp: str = ""
    paths: list = _path.split(PathSeparator)

    for path_field in paths:
        path_temp += (path_field + PathSeparator)

        if not os.path.exists(path=path_temp):
            os.mkdir(path=path_temp)


def get_file(FileLock: Lock) -> str:
    """
    返回文件名 (FileCount + ".jpg" 格式) 

    在查看 FileCount 并自增时上锁, 完毕后解锁
    """
    FileLock.acquire()      # 上锁
    
    global FileCount

    # 读值
    path: str = "%d.jpg" % FileCount
    FileCount += 1          # 自增

    FileLock.release()      # 解锁

    return path


class WallPaperSpider:
    """
    壁纸爬虫类
    """
    
    """
    同时只能爬取同一个网址

    但是内含的图片的地址可以储存在一个 Queue 对象中, 
        每次可以开启多个线程进行下载并保存

    下载时的路径应该为一个文件夹路径, 应该在类的外部编写一个函数来检测文件夹是否存在否则就创建
    保存的文件名应该依次为 1.jpg, 2.jpg, 等

    为了避免由于文件名混乱而导致的文件写入错误, 应该在全局设置一个 FileCount 变量,
        改变量从 1 开始, 并且设置一个 get_file() 函数, 用于获得当前的 FileCou-
        nt 的数量并生成一个文件名 (1.jpg, 2.jpg, ...)并返回, 该函数内部应该含有
        一个 Lock() (这个 Lock 应该为全局变量)
    """
    def __init__(self) -> None:
        # 状态相关变量
        self.status: int = 0            # 状态码 (1表示要爬取知乎网站, 2表示要爬取哔哩哔哩网站, 0表示未初始化)

        # 爬取网址相关变量
        self.url: str = ""              # 要爬取的网址
        self.pic_urls: Queue = Queue()  # 当前页面上的壁纸的地址

        # 网站爬取相关变量
        self.headers: dict = {          # 爬虫请求头
            "User-Agent": 
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/107.0.0.0 Safari/537.36"
            }

        # 线程相关变量
        self.thread_num: int = 1        # 开启的线程数量

        # 保存相关变量
        self.path: str = None           # 图片保存目录 (应该为文件夹)

    def set_url(self, _url: str) -> bool:
        """
        设置要爬取的网址为 _url

        返回: bool (设置成功返回 True, 失败返回 False)
        """
        _url = _url.strip()

        if not (_url.startswith("https://") or _url.startswith("http://")):
            _url = ("https://" + _url)

        if ("zhihu.com" in _url) or ("bilibili.com" in _url):
            if "zhihu.com" in _url:
                self.status = 1
            else:
                self.status = 2

            self.url = _url

            return True
        else:
            return False

    def save(self, _urls: list, __name: str) -> None:
        global FileLock
        global get_file

        for _url in _urls:
            if _url.endswith(".png"):
                continue

            _path: str = self.path + PathSeparator + get_file(FileLock=FileLock)

            try:
                pic_source: bytes = urlopen(Request(url=_url, headers=self.headers)).read()
                # pic_source: 图片内容 (二进制形式)

                with open(_path, "wb") as file:
                    file.write(pic_source)

            except Exception:
                print("%s: 保存 %s 时出错, 正在进行下一任务..." % (__name, _url), end="\n")

            else:
                print("%s: 已将 %s 写入到 %s 中" % (__name, _url, _path), end="\n")

            finally:
                continue

        return

    def hand_up(self) -> None:
        """
        开启线程, 爬取并保存图片
        """
        threads: list = list()

        url_num: int = (self.pic_urls.qsize() // self.thread_num) + 1

        for count in range(self.thread_num):
            _urls: list = []
            for _ in range(url_num):
                if not self.pic_urls.empty():
                    _urls.append(self.pic_urls.get_nowait())

            _name="THREAD-%d" % (count + 1)

            # "创造"线程
            threads.append(Thread(target=self.save, name=_name,
                                     args=(_urls, _name)))
            
        # "启动"线程
        for thread in threads:
            thread.start()
        
        for thread in threads:
            thread.join()

    def run(self) -> bool:
        """
        开始将网址为 self.url 的网站中的壁纸保存在 self.path 中

        返回: 成功返回 True, 失败返回 False
        """
        if self.status == 0:
            # 未初始化 (一般不会发生, 但是为了以防万一设置这个判断)
            return False

        """ 以下代码: 获得网站中的壁纸地址并保存在 self.pic_urls 中 """

        requester: Request = Request(url=self.url, headers=self.headers)
        opener: HTTPResponse = urlopen(requester)

        url_source: str = opener.read().decode("utf-8")     # url_source: 网站源代码

        if self.status == 1:
            # 爬取知乎网址
            pattern: str = "data-original=\"(.*?)\""

            # 由于在知乎网站中, 同一个地址会出现两次, 因此使用以下方法进行判断是否重复
            result: list = re.findall(pattern=pattern, string=url_source, flags=re.S)
            url_temp: str = None

            for url_now in result:
                if url_now != url_temp:
                    url_now = url_now.strip()

                    self.pic_urls.put_nowait(url_now)

                    print("正在添加: %s" % url_now, end='\n')

                    url_temp = url_now

        elif self.status == 2:
            # 爬取哔哩哔哩网址
            pattern: str = "img data-src=\"(.*?)\""

            # 由于在哔哩哔哩网站中, 壁纸地址前没有 "https:", 因此要手动添加
            for url in re.findall(pattern=pattern, string=url_source, flags=re.S):
                url = url.strip()

                self.pic_urls.put_nowait("https:" + url.strip())

                print("正在添加: %s" % url, end='\n')
        
        """ END """

        """ 确定线程数量 """
        if self.pic_urls.qsize() <= 10:
            self.thread_num = 1
        
        else:
            thread_num: int = input("将会下载 %d 张壁纸, 您希望开启多少个线程: " % self.pic_urls.qsize())
            while 1:
                try:
                    thread_num = int(thread_num)
                
                except ValueError:
                    thread_num: int = input("请正确输入: ")
                
                else:
                    break

            self.thread_num = thread_num

        """ END """

        """ 开始保存图片 """

        self.hand_up()

        """ END """


def main() -> None:
    """
    程序引擎
    """
    spider: WallPaperSpider = WallPaperSpider()

    url = input("请输入要下载壁纸的网址: (目前只支持知乎网和哔哩哔哩网)\n")
    while not spider.set_url(_url=url):
        url = input("请正确输入: \n")

    path: str = input("您希望将图片保存在哪里: (不存在的文件夹将会自动创建)\n")
    while 1:
        try:
            mkdir(path)

        except:
            path = input("请正确输入: \n")
        
        else:
            spider.path = path

            break

    spider.run()

    print("\n\n完毕...\n")


if __name__ == "__main__":
    """
    程序入口
    """
    main()

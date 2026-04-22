1. selenium 访问网址: https://smartcourse.hust.edu.cn/mooc2-ans/mooc2-ans/mycourse/stu?courseid=17310000022966&clazzid=17310000017957&cpi=17310000158138&enc=aee62e8272614c543b585c3dd58ceec4&t=1776855970261&pageHeader=1
2. 用户登录, 访问视频页面, 回车, 在当前最上方的页面开始以下循环

循环:

点击播放: 
/html/body/div[2]/div[1]/div[3]/div[2]/div/button

监测进度条是否播放完: 
- 当前观看时长: /html/body/div[2]/div[1]/div[3]/div[2]/div/div[6]/div[2]/span[2]
- 总时长: /html/body/div[2]/div[1]/div[3]/div[2]/div/div[6]/div[4]/span[2]

播放完点击下一节: /html/body/div[6]/div/div[3]/div[8]/div[1]

如果出现这个元素, 点击: /html/body/div[6]/div/div[3]/div[1]/div/div[3]/a[2]
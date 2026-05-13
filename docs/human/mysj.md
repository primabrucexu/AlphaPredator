# 麦蕊数据接入说明

麦蕊数据是我们的A股市场数据提供商

## 用途

获取市场天级别交易数据

## 访问方式

通过api接口进行访问，详见接口文档[mysj.yaml](api-docs/mysj.yaml)

## 认证方式

在url参数中拼接licence字段，值为麦蕊数据提供的授权码。需要用户通过配置输入

## 访问频率限制

- 单个接口不超过每分钟300次

## 接口访问范围

由于麦蕊数据提供了各方面的数据接口，为了避免冗余代码，结合当前项目需求，我们仅需要访问下面几个接口

- 股票列表
- 按照天的维度获取历史分时交易

## 数据保存方式

数据写入duckdb数据库的day_level_trade_data表，详细见[AlphaPredator.dbml](data-model/AlphaPredator.dbml)
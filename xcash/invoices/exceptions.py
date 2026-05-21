class InvoiceStatusError(Exception):
    """账单状态不满足操作前置条件时抛出。"""


class InvoiceAllocationError(Exception):
    """账单无法分配收款地址/金额组合时抛出。"""


class InvoiceBillingModeError(Exception):
    """账单计费模式与所请求动作不匹配时抛出。"""


class InvoiceCollectionError(Exception):
    """合约账单触发归集前置条件不满足时抛出。"""

import json

from consts import MIN_BOX_VALUE, MAX_BORROW_TOKENS, TX_FEE
from helpers.job_helpers import latest_pool_info, job_processor
from helpers.node_calls import box_id_to_binary, sign_tx
from logger import set_logger

logger = set_logger(__name__)


def process_repay_to_pool_box(pool, box, latest_tx):
    pool_box, borrowed = latest_pool_info(pool, latest_tx)
    box_id = box.get('boxId', 'unknown')
    transaction_id = box.get('transactionId', 'unknown')
    explorer_url = f"https://ergexplorer.com/boxes#{box_id}" if box_id != 'unknown' else None

    if "assets" not in box or len(box["assets"]) < 2:
        if explorer_url:
            logger.error(f"[Repay to Pool SUSD] Box has insufficient assets. Transaction ID: {transaction_id}, Box ID: {box_id}. Check the box on Erg Explorer: {explorer_url}. If this persists, verify the bot's configuration or contact Duckpools support on Discord.")
        else:
            logger.error(f"[Repay to Pool SUSD] Box has insufficient assets. Transaction ID: {transaction_id}, Box ID: unknown. Unable to provide Erg Explorer link. Please verify the bot's configuration or contact Duckpools support on Discord.")
        return None

    try:
        assets_to_give = box["assets"][1]["amount"]
        final_borrowed = borrowed - int(box["assets"][0]["amount"])
    except (ValueError, TypeError) as e:
        logger.error(f"[Repay to Pool SUSD] Invalid asset amount: {e}. Transaction ID: {transaction_id}, Box ID: {box_id}. Check the box on Erg Explorer: {explorer_url}. If this persists, contact Duckpools support on Discord.")
        return None

    transaction_to_sign = \
        {
            "requests": [
                {
                    "address": pool["pool"],
                    "value": pool_box["value"] + MIN_BOX_VALUE,
                    "assets": [
                        {
                            "tokenId": pool_box["assets"][0]["tokenId"],
                            "amount": pool_box["assets"][0]["amount"]
                        },
                        {
                            "tokenId": pool_box["assets"][1]["tokenId"],
                            "amount": pool_box["assets"][1]["amount"]
                        },
                        {
                            "tokenId": pool_box["assets"][2]["tokenId"],
                            "amount": MAX_BORROW_TOKENS - final_borrowed
                        },
                        {
                            "tokenId": pool_box["assets"][3]["tokenId"],
                            "amount": pool_box["assets"][3]["amount"] + assets_to_give
                        }
                    ],
                    "registers": {
                    }
                },
            ],
            "fee": TX_FEE,
            "inputsRaw":
                [box_id_to_binary(pool_box["boxId"]), box_id_to_binary(box["boxId"])],
            "dataInputsRaw":
                []
        }

    logger.debug("Signing Transaction: %s", json.dumps(transaction_to_sign))
    tx_id = sign_tx(transaction_to_sign)

    obj = {"txId": tx_id,
           "finalBorrowed": final_borrowed}
    if tx_id != -1:
        logger.info("Successfully submitted transaction with ID: %s", tx_id)
    else:
        logger.debug("Failed to submit transaction")
        return None
    return obj


def t_repay_to_pool_job(pool, curr_tx_obj):
    job_processor(pool, pool["repayment"], curr_tx_obj, process_repay_to_pool_box, "repay to pool")

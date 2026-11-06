from fastapi.responses import JSONResponse
from fastapi.encoders import jsonable_encoder


def success_response(message: str, data=None):
    return JSONResponse(
        content=jsonable_encoder({
            "code": 200,
            "message": message,
            "data": data
        })
    )

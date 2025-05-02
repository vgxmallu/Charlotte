# Charlottes Error Codes

Charlotte have a several error codes for standardization and safety. Here are all the codes that can be used to output an error and a description of each.

Error handler located at utils/error_handler.py

##  Class BotError

Custom exception for centralized error handling in the bot. Allows you to control which errors are sent to the user and which are sent to the bot owner.

```python
class BotError(Exception):
    def __init__(self, code: str, message: str, url: Optional[str] = None, critical: bool = False, is_logged: bool = False):
```
Parametrs:

| Параметр |	Тип | 	Описание |
| -------- | -------- | -------- |
 | code |	str |	A unique error code (e.g., “E001”). |
| message |	str |	Detailed message to the owner (logging, PM). |
 | url |	Optional[str] |	The URL of the media file with which the error occurred (default is “None”). |
| critical |	bool |	If True, the error will be sent to the owner in a PM. |
| is_logged |	bool |	If True, the error will be logged into log file. |

Attributes:

- code: error code.
- url: URL of the linked content.
- message: error text for the owner.
- critical: criticality flag.
- is_logged: logged flag.

## Класс ErrorCode

A set of predefined error codes used in BotError.
```python
class ErrorCode:
    INVALID_URL = "E001"
    LARGE_FILE = "E002"
    SIZE_CHECK_FAIL = "E003"
    DOWNLOAD_FAILED = "E004"
    DOWNLOAD_CANCELLED = "E005"
    PLAYLIST_INFO_ERROR = "E006"
    INTERNAL_ERROR = "E500"
```

Список кодов:


|Код |	Название | 	Описание |
| -------- | -------- | -------- |
|E001 |	INVALID_URL |	Occurs when user provides invalid url. Invalid links are those that pass the initial filter but either lack the media ID needed for downloading, or refer to content that no longer exists or has been made private.|
|E002 |	LARGE_FILE |	Occurs when downloaded media file is too large and it can't be uploaded into Telegram. |
|E003 |	SIZE_CHECK_FAIL |	The error occurs when the estimated file size during the pre-check exceeds 50 MB. |
|E004 |	DOWNLOAD_FAILED |	The error occurs when a media download fails for some reason. |
|E005 |	DOWNLOAD_CANCELLED |	The error occurs when download is cancelled. It's a crutch, ignore it. |
|E006 |	PLAYLIST_INFO_ERROR |	The error occurs when playlist information could not be retrieved. |
|E500 |	INTERNAL_ERROR |	Global eror code. Occurs if the error cannot be described by the codes above. |


## Usage Example:

```python
if not is_valid_url(url):
    raise BotError(
        code=ErrorCode.INVALID_URL,
        message=f"Invalid URL provided",
        url=url,
        critical=False
    )
```

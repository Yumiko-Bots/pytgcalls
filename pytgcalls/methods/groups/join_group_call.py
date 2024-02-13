import logging
from typing import(
         Any, Optional, 
         Union)

from ntgcalls import(
         ConnectionError, FileError, 
         InvalidParams, TelegramServerError
)

from ...exceptions import(
         AlreadyJoinedError, ClientNotStarted, 
         NoActiveGroupCall, NoMTProtoClientSet, 
         UnMuteNeeded
)
from ...mtproto import BridgedClient
from ...scaffold import Scaffold
from ...statictypes import statictypes
from ...to_async import ToAsync
from ...types.raw.stream import Stream
from ..utilities.stream_params import StreamParams

py_logger = logging.getLogger('pytgcalls')


class JoinGroupCall(Scaffold):
    @statictypes
    async def join_group_call(
        self,
        chat_id: Union[int, str],
        stream: Optional[Stream] = None,
        invite_hash: Optional[str] = None,
        join_as: Any = None,
        auto_start: bool = True,
    ):
        if join_as is None:
            join_as = self._cache_local_peer

        chat_id = await self._resolve_chat_id(chat_id)
        self._cache_user_peer.put(chat_id, join_as)

        if self._app is None:
            raise NoMTProtoClientSet()

        if not self._is_running:
            raise ClientNotStarted()

        chat_call = await self._app.get_full_chat(chat_id)
        if chat_call is None:
            if auto_start:
                await self._app.create_group_call(chat_id)
            else:
                raise NoActiveGroupCall()     
        # Ensure the 'Start' class is initialized and running
        start_instance = Start()
        await start_instance.start()

        media_description = await StreamParams.get_stream_params(stream)

        try:
            for retries in range(4):
                call_params: str = await ToAsync(
                    start_instance._binding.create_call,
                    chat_id,
                    media_description,
                )

                try:
                    result_params = await self._app.join_group_call(
                        chat_id,
                        call_params,
                        invite_hash,
                        media_description.video is None,
                        self._cache_user_peer.get(chat_id),
                    )
                    await ToAsync(
                        start_instance._binding.connect,
                        chat_id,
                        result_params,
                    )
                    break
                except TelegramServerError:
                    if retries == 3:
                        raise
                    if retries >= 1:
                        py_logger.warning(
                            f'Telegram is having some internal server issues. '
                            f'Retrying {retries + 1} of 3',
                        )

            participants = await self._app.get_group_call_participants(chat_id)

            for x in participants:
                if x.user_id == BridgedClient.chat_id(self._cache_local_peer) and x.muted_by_admin:
                    start_instance._need_unmute.add(chat_id)
        except FileError:
            raise FileNotFoundError()
        except ConnectionError:
            raise AlreadyJoinedError()
        except InvalidParams:
            raise UnMuteNeeded()

from aiogram.fsm.state import State, StatesGroup

class AddMediaState(StatesGroup):
    category = State()
    title = State()
    original_title = State()
    poster = State()
    genre = State()
    year = State()
    duration = State()
    language = State()
    age_rating = State()
    description = State()
    code = State()
    is_premium = State()
    file = State()

class AddEpisodeState(StatesGroup):
    media_code = State()
    episode_num = State()
    title = State()
    file = State()

class DeleteMediaState(StatesGroup):
    code = State()

class AccessMediaState(StatesGroup):
    code = State()

class BlockUserState(StatesGroup):
    user_id = State()

class UnblockUserState(StatesGroup):
    user_id = State()

class AddAdminState(StatesGroup):
    user_id = State()

class RemoveAdminState(StatesGroup):
    user_id = State()

class GrantPremiumState(StatesGroup):
    user_id = State()
    days = State()

class SearchMediaState(StatesGroup):
    query = State()
    code_only = State()

class BatchUploadState(StatesGroup):
    media_code = State()
    start_ep = State()
    free_up_to = State()
    uploading = State()

class EpisodeAccessState(StatesGroup):
    media_code = State()
    free_up_to = State()

class ChannelMgmtState(StatesGroup):
    channel_id = State()
    channel_name = State()
    invite_link = State()
    del_channel = State()

class MovieRequestState(StatesGroup):
    title = State()

class ChannelPostState(StatesGroup):
    channel_id = State()

class PremiumSettingsState(StatesGroup):
    edit_uzs_1m = State()
    edit_uzs_3m = State()
    edit_uzs_1y = State()
    edit_stars_1m = State()
    edit_stars_3m = State()
    edit_stars_1y = State()
    edit_payment_admin = State()
    edit_card_details = State()


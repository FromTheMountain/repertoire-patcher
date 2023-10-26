# TODO: add up the probabilities of two lines whenever they transpose into each other, as opposed to 
# treating them as completely separate positions. Display both lines in the final program output, but 
# only count once towards the num_positions.

from collections import namedtuple
import datetime
import json
import time
from typing import Optional
import chess
import chess.pgn
import requests

class PositionNode:
    def __init__(self, position: chess.Board, probability: float) -> None:
        self.board: chess.Board = position
        self.probability: float = probability

class Repertoire:
    def __init__(self, pgn_file_path: str, is_black: bool) -> None:
        self.response_map: dict[str, chess.Move] = dict()

        with open(pgn_file_path) as pgn_file:
            while True:
                # Loop through the games (or lichess study chapters) in the PGN file
                game: chess.pgn.Game = chess.pgn.read_game(pgn_file)

                if game is None:
                    break

                pgn_nodes: list[chess.pgn.GameNode] = \
                    game.variations if is_black else [game]

                while pgn_nodes:
                    node: chess.pgn.GameNode = pgn_nodes.pop()
                    board: chess.Board = node.board()

                    # TODO: allow the program to work even if multiple variations are defined in response to one.
                    # Maybe print a warning, but do not throw an exception. This will require changing the response_map
                    # from a dict[str, chess.Move] to a dict[str, list[chess.Move]] - or maybe a dict[str, set[chess.Move]]
                    if len(node.variations) > 1:
                        raise Exception(f"Multiple moves defined at position after {board.move_stack}")

                    if len(node.variations) == 0:
                        continue

                    self.response_map[board.fen()] = node.variation(0).move

                    pgn_nodes.extend(node.variation(0).variations)

class LichessApiCaller:
    def __init__(self):
        self.last_call_time: Optional[datetime.datetime] = None

    def delay_call(self):
        if self.last_call_time is not None:
            now = datetime.datetime.now()
            time_since_last_call: datetime.timedelta = now - self.last_call_time

            if time_since_last_call < datetime.timedelta(seconds=0.5):
                time.sleep(0.5 - time_since_last_call.total_seconds())
        
        self.last_call_time = datetime.datetime.now()

    def call_api(self, board: chess.Board):
        self.delay_call()

        response: requests.Response = requests.get(f"https://explorer.lichess.ovh/masters?fen={board.fen()}")
        response_object: any = json.loads(response.text)

        return response_object


api_caller = LichessApiCaller()

def get_most_common_moves_from_lichess(board: chess.Board) -> list[tuple[str, float]]:
    response_object: any = api_caller.call_api(board)

    total_num_games: int = response_object["white"] + response_object["draws"] + response_object["black"]

    move_list: list[tuple[str, float]] = list()

    for move in response_object["moves"]:
        variation_num_games: int = move["white"] + move["draws"] + move["black"]

        relative_probability: float = variation_num_games / total_num_games

        move_list.append((move["uci"], relative_probability))

    return move_list

"""
Returns an unsorted list of the most common positions that may occur one move after
the given position, along with the absolute probability that this position arises in a game.
"""
def get_most_common_positions(position: PositionNode) -> list[PositionNode]:
    next_moves = get_most_common_moves_from_lichess(position.board)
    next_positions: list[PositionNode] = list()
    
    # Assume that each position has a SAN and a probability
    for next_move in next_moves:
        next_board: chess.Board = position.board.copy()
        next_board.push_uci(next_move[0])

        next_probability: float = position.probability * next_move[1]

        next_positions.append(PositionNode(next_board, next_probability))        
    
    return next_positions

def pop_most_probable_node(leaf_positions: list[PositionNode]) -> PositionNode:
    max_idx: Optional[int] = None
    max_probability: float = 0
    
    for idx, position in enumerate(leaf_positions):
        if position.probability > max_probability:
            max_probability = position.probability
            max_idx = idx

    assert max_idx is not None

    if max_idx is None:
        raise Exception("There is no position that arises with positive probability")

    return leaf_positions.pop(max_idx)
        
"""
Looks up the move that is played in the repertoire in this position. Pushes the move to
the board and returns True if it was found, returns False otherwise without touching the 
board.
"""        
def play_repertoire_move(repertoire: Repertoire, board: chess.Board) -> bool:
    try:
        move: chess.Move = repertoire.response_map[board.fen()]
        board.push(move)
        return True
    except KeyError:
        return False

def get_most_common_unknown_positions(pgn_file_path: str, is_black: bool, num_positions: int):
    repertoire: Repertoire = Repertoire(pgn_file_path, is_black)

    initial_position = PositionNode(chess.Board(), 1)

    leaf_positions: list[PositionNode] = \
        get_most_common_positions(initial_position) if is_black else [initial_position]

    unknown_positions: list[PositionNode] = list()
    
    while leaf_positions:
        node = pop_most_probable_node(leaf_positions)

        # Check if a response to this position is available
        repertoire_move_exists: bool = play_repertoire_move(repertoire, node.board)

        if repertoire_move_exists:
            leaf_positions.extend(get_most_common_positions(node))
        else:
            unknown_positions.append(node)

            if len(unknown_positions) == num_positions:
                return unknown_positions

    return unknown_positions

if __name__ == "__main__":
    unknown_positions: list[PositionNode] = get_most_common_unknown_positions(
        "/home/jeroenvdb/Downloads/lichess_study_black-repertoire_by_MessyAnswer_2022.07.05.pgn",
        True,
        10
    )

    for node in unknown_positions:
        print(f"{node.probability:0.2f}: ", end="")

        game: chess.pgn.Game = chess.pgn.Game.from_board(node.board)

        exporter: chess.pgn.StringExporter = chess.pgn.StringExporter(headers=False, variations=False, comments=False)
        print(game.accept(exporter))
        
"""
Conversations command for voice-mode CLI.
"""

import sys
from datetime import datetime, timedelta
from typing import Optional

import click

from voice_mode.exchanges import (
    ExchangeReader, 
    ConversationGrouper,
    ExchangeFormatter
)


@click.command()
@click.option('-n', '--lines', type=int, default=20,
              help='Number of conversations to show')
@click.option('--today', is_flag=True, help="Show today's conversations")
@click.option('--yesterday', is_flag=True, help="Show yesterday's conversations")
@click.option('-d', '--date', type=click.DateTime(formats=['%Y-%m-%d']),
              help='Show specific date')
@click.option('--days', type=int, help='Show last N days')
@click.option('-f', '--format', 
              type=click.Choice(['simple', 'detailed', 'json', 'csv']), 
              default='simple',
              help='Output format')
@click.option('--min-exchanges', type=int, default=1,
              help='Minimum exchanges per conversation')
@click.option('--min-duration', type=int,
              help='Minimum duration in seconds')
@click.option('--reverse', is_flag=True, help='Show oldest first')
@click.option('--no-color', is_flag=True, help='Disable colored output')
def conversations(lines, today, yesterday, date, days, format, min_exchanges, 
                 min_duration, reverse, no_color):
    """List conversations with summary information.
    
    Shows conversations one per line with ID, timestamp, duration,
    exchange count, and preview of first message.
    """
    reader = ExchangeReader()
    grouper = ConversationGrouper()
    formatter = ExchangeFormatter()
    
    # Determine which exchanges to read
    if today:
        exchanges = list(reader.read_date(datetime.now().date()))
    elif yesterday:
        yesterday_date = datetime.now().date() - timedelta(days=1)
        exchanges = list(reader.read_date(yesterday_date))
    elif date:
        exchanges = list(reader.read_date(date.date()))
    elif days:
        exchanges = list(reader.read_recent(days))
    else:
        # Default to last 7 days
        exchanges = list(reader.read_recent(7))
    
    if not exchanges:
        click.echo("No exchanges found in the specified period.", err=True)
        return
    
    # Group into conversations
    conversations = grouper.group_exchanges(exchanges)
    
    # Filter conversations
    filtered_convs = []
    for conv in conversations.values():
        if conv.exchange_count < min_exchanges:
            continue
        if min_duration and conv.duration.total_seconds() < min_duration:
            continue
        filtered_convs.append(conv)
    
    # Sort conversations
    filtered_convs.sort(key=lambda c: c.start_time, reverse=not reverse)
    
    # Limit number shown
    if lines and len(filtered_convs) > lines:
        filtered_convs = filtered_convs[:lines]
    
    # Handle color
    use_color = not no_color and sys.stdout.isatty()
    
    # Format and output
    if format == 'simple':
        for conv in filtered_convs:
            # Get first user message for preview
            preview = ""
            for exchange in conv.exchanges:
                if exchange.type == 'stt':
                    preview = exchange.text[:60] + "..." if len(exchange.text) > 60 else exchange.text
                    break
            
            # Format duration
            duration_seconds = conv.duration.total_seconds()
            duration_str = f"{int(duration_seconds)}s"
            if duration_seconds >= 60:
                minutes = int(duration_seconds / 60)
                seconds = int(duration_seconds % 60)
                duration_str = f"{minutes}m{seconds}s"
            
            # Format line
            if use_color:
                line = (
                    f"\033[36m{conv.id}\033[0m  "  # Cyan for ID
                    f"\033[90m{conv.start_time.strftime('%Y-%m-%d %H:%M:%S')}\033[0m  "  # Gray for time
                    f"{conv.exchange_count:3d} exchanges  "
                    f"{duration_str:>6s}  "
                    f"\033[37m{preview}\033[0m"  # White for preview
                )
            else:
                line = (
                    f"{conv.id}  "
                    f"{conv.start_time.strftime('%Y-%m-%d %H:%M:%S')}  "
                    f"{conv.exchange_count:3d} exchanges  "
                    f"{duration_str:>6s}  "
                    f"{preview}"
                )
            
            print(line)
    
    elif format == 'detailed':
        for i, conv in enumerate(filtered_convs):
            if i > 0:
                print()  # Blank line between conversations
            
            print(f"Conversation: {conv.id}")
            print(f"Started: {conv.start_time}")
            print(f"Duration: {conv.duration}")
            print(f"Exchanges: {conv.exchange_count} (STT: {conv.stt_count}, TTS: {conv.tts_count})")
            word_count = sum(len(e.text.split()) for e in conv.exchanges)
            print(f"Word Count: {word_count}")
            
            # Show first few exchanges
            print("First exchanges:")
            for j, exchange in enumerate(conv.exchanges[:3]):
                prefix = "  User: " if exchange.type == 'stt' else "  Assistant: "
                text = exchange.text[:100] + "..." if len(exchange.text) > 100 else exchange.text
                print(f"{prefix}{text}")
            
            if conv.exchange_count > 3:
                print(f"  ... and {conv.exchange_count - 3} more exchanges")
    
    elif format == 'json':
        import json
        conv_list = []
        for conv in filtered_convs:
            conv_dict = {
                'id': conv.id,
                'start_time': conv.start_time.isoformat(),
                'end_time': conv.end_time.isoformat(),
                'duration_seconds': conv.duration.total_seconds(),
                'exchange_count': conv.exchange_count,
                'stt_count': conv.stt_count,
                'tts_count': conv.tts_count,
                'word_count': sum(len(e.text.split()) for e in conv.exchanges),
                'first_message': conv.exchanges[0].text[:100] if conv.exchanges else ""
            }
            conv_list.append(conv_dict)
        
        print(json.dumps(conv_list, indent=2))
    
    elif format == 'csv':
        # CSV header
        print("conversation_id,start_time,duration_seconds,exchange_count,stt_count,tts_count,word_count,first_message")
        
        for conv in filtered_convs:
            first_msg = conv.exchanges[0].text[:100].replace('"', '""') if conv.exchanges else ""
            print(f'"{conv.id}","{conv.start_time}",{conv.duration.total_seconds()},'
                  f'{conv.exchange_count},{conv.stt_count},{conv.tts_count},'
                  f'{sum(len(e.text.split()) for e in conv.exchanges)},"{first_msg}"')
    
    # Summary
    if format in ['simple', 'detailed']:
        print(f"\n{len(filtered_convs)} conversations shown", file=sys.stderr)


if __name__ == '__main__':
    conversations()
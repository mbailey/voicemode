"""
Exchanges command group for voice-mode CLI.
"""

import sys
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import click

from voice_mode.exchanges import (
    ExchangeReader, 
    ExchangeFormatter, 
    ExchangeFilter,
    ConversationGrouper,
    ExchangeStats
)


@click.group()
def exchanges():
    """Manage and view conversation exchange logs."""
    pass


@exchanges.command()
@click.option('-f', '--format', 
              type=click.Choice(['simple', 'pretty', 'json', 'raw']), 
              default='simple',
              help='Output format')
@click.option('--stt', is_flag=True, help='Show only STT entries')
@click.option('--tts', is_flag=True, help='Show only TTS entries')
@click.option('-F', '--full', is_flag=True, help='Show full metadata')
@click.option('--no-color', is_flag=True, help='Disable colored output')
@click.option('-d', '--date', type=click.DateTime(formats=['%Y-%m-%d']), 
              help='Tail specific date (default: today)')
@click.option('--transport', 
              type=click.Choice(['local', 'livekit', 'speak-only', 'all']),
              help='Filter by transport type')
@click.option('--provider', help='Filter by provider')
def tail(format, stt, tts, full, no_color, date, transport, provider):
    """Real-time following of exchange logs."""
    reader = ExchangeReader()
    formatter = ExchangeFormatter()
    filter_obj = ExchangeFilter()
    
    # Apply filters
    if stt:
        filter_obj.by_type('stt')
    elif tts:
        filter_obj.by_type('tts')
    
    if transport and transport != 'all':
        filter_obj.by_transport(transport)
    
    if provider:
        filter_obj.by_provider(provider)
    
    # Handle color
    use_color = not no_color and sys.stdout.isatty()
    
    try:
        # Tail the logs
        for exchange in filter_obj.apply(reader.tail(follow=True)):
            if format == 'simple':
                output = formatter.simple(exchange, color=use_color, show_timing=not full)
            elif format == 'pretty':
                output = formatter.pretty(exchange, show_metadata=full)
            elif format == 'json':
                output = formatter.json(exchange)
            elif format == 'raw':
                output = exchange.to_jsonl()
            
            print(output)
            
            if format == 'pretty':
                print()  # Extra line between pretty entries
            
            sys.stdout.flush()
    
    except KeyboardInterrupt:
        # Clean exit on Ctrl+C
        pass


@exchanges.command()
@click.option('-n', '--lines', type=int, default=20,
              help='Number of exchanges to show')
@click.option('-c', '--conversation', help='Show specific conversation')
@click.option('--today', is_flag=True, help="Show today's exchanges")
@click.option('--yesterday', is_flag=True, help="Show yesterday's exchanges")
@click.option('-d', '--date', type=click.DateTime(formats=['%Y-%m-%d']),
              help='Show specific date')
@click.option('-f', '--format', 
              type=click.Choice(['simple', 'pretty', 'json']), 
              default='simple',
              help='Output format')
@click.option('--reverse', is_flag=True, help='Show oldest first')
@click.option('--no-color', is_flag=True, help='Disable colored output')
def view(lines, conversation, today, yesterday, date, format, reverse, no_color):
    """View recent exchanges without tailing."""
    reader = ExchangeReader()
    formatter = ExchangeFormatter()
    
    # Determine which exchanges to show
    if conversation:
        exchanges = reader.read_conversation(conversation)
    elif today:
        exchanges = list(reader.read_date(datetime.now().date()))
    elif yesterday:
        yesterday_date = datetime.now().date() - timedelta(days=1)
        exchanges = list(reader.read_date(yesterday_date))
    elif date:
        exchanges = list(reader.read_date(date.date()))
    else:
        exchanges = reader.get_latest_exchanges(lines)
    
    # Apply reverse if requested
    if not reverse:
        exchanges = list(reversed(exchanges))
    
    # Handle color
    use_color = not no_color and sys.stdout.isatty()
    
    # Format and output
    for exchange in exchanges[-lines:] if not conversation else exchanges:
        if format == 'simple':
            output = formatter.simple(exchange, color=use_color)
        elif format == 'pretty':
            output = formatter.pretty(exchange)
        elif format == 'json':
            output = formatter.json(exchange)
        
        print(output)
        
        if format == 'pretty':
            print()  # Extra line between pretty entries


@exchanges.command()
@click.argument('query')
@click.option('-n', '--max-results', type=int, default=50,
              help='Maximum results to show')
@click.option('-d', '--days', type=int, default=7,
              help='Number of days to search')
@click.option('--type', 'exchange_type',
              type=click.Choice(['stt', 'tts', 'all']),
              default='all',
              help='Search specific type')
@click.option('--regex', is_flag=True, help='Use regex search')
@click.option('-i', '--ignore-case', is_flag=True, default=True,
              help='Case insensitive search')
@click.option('--conversation', is_flag=True, 
              help='Show full conversations')
@click.option('-f', '--format', 
              type=click.Choice(['simple', 'json']), 
              default='simple',
              help='Output format')
@click.option('--no-color', is_flag=True, help='Disable colored output')
def search(query, max_results, days, exchange_type, regex, ignore_case, 
           conversation, format, no_color):
    """Search through exchange logs."""
    reader = ExchangeReader()
    formatter = ExchangeFormatter()
    filter_obj = ExchangeFilter()
    grouper = ConversationGrouper()
    
    # Set up filters
    filter_obj.by_text(query, regex=regex, ignore_case=ignore_case)
    if exchange_type != 'all':
        filter_obj.by_type(exchange_type)
    
    # Read exchanges from recent days
    exchanges = list(filter_obj.apply(reader.read_recent(days)))
    
    if conversation:
        # Group by conversation and show full conversations
        conversations = grouper.group_exchanges(exchanges)
        shown_conversations = set()
        results_count = 0
        
        for exchange in exchanges:
            if exchange.conversation_id not in shown_conversations:
                conv = conversations[exchange.conversation_id]
                
                # Show conversation header
                print(f"\n=== Conversation {conv.id} ===")
                print(f"Duration: {conv.duration} | Exchanges: {conv.exchange_count}")
                print()
                
                # Show all exchanges in conversation
                for conv_exchange in conv.exchanges:
                    if format == 'simple':
                        output = formatter.simple(conv_exchange, 
                                                color=not no_color and sys.stdout.isatty())
                    else:
                        output = formatter.json(conv_exchange)
                    print(output)
                
                shown_conversations.add(exchange.conversation_id)
                results_count += 1
                
                if results_count >= max_results:
                    break
    else:
        # Show individual matching exchanges
        for i, exchange in enumerate(exchanges[:max_results]):
            if format == 'simple':
                output = formatter.simple(exchange, 
                                        color=not no_color and sys.stdout.isatty())
            else:
                output = formatter.json(exchange)
            print(output)
    
    # Summary
    total_found = len(exchanges)
    shown = min(total_found, max_results)
    print(f"\n{shown} of {total_found} results shown", file=sys.stderr)


@exchanges.command()
@click.option('-d', '--days', type=int, help='Stats for last N days')
@click.option('--by-hour', is_flag=True, help='Group by hour')
@click.option('--by-provider', is_flag=True, help='Group by provider')
@click.option('--by-transport', is_flag=True, help='Group by transport')
@click.option('--timing', is_flag=True, help='Show timing statistics')
@click.option('--conversations', is_flag=True, help='Show conversation stats')
@click.option('--errors', is_flag=True, help='Show error statistics')
@click.option('--silence', is_flag=True, help='Show silence detection stats')
@click.option('--all', 'show_all', is_flag=True, help='Show all statistics')
def stats(days, by_hour, by_provider, by_transport, timing, conversations, 
          errors, silence, show_all):
    """Show statistics about exchanges."""
    reader = ExchangeReader()
    
    # Read exchanges
    if days:
        exchanges = list(reader.read_recent(days))
    else:
        # Default to last 7 days
        exchanges = list(reader.read_recent(7))
    
    if not exchanges:
        click.echo("No exchanges found in the specified period.", err=True)
        return
    
    stats_obj = ExchangeStats(exchanges)
    
    # If no specific stats requested, show summary
    if not any([by_hour, by_provider, by_transport, timing, conversations, 
                errors, silence]) or show_all:
        print(stats_obj.get_summary_report())
        return
    
    # Show specific stats
    if by_hour or show_all:
        print("\nHourly Distribution:")
        print("-" * 30)
        hourly = stats_obj.hourly_distribution()
        for hour, count in sorted(hourly.items()):
            bar = '█' * (count // 5) if count > 0 else ''
            print(f"{hour:02d}:00  {count:4d}  {bar}")
    
    if by_provider or show_all:
        print("\nProvider Breakdown:")
        print("-" * 30)
        for provider, count in stats_obj.provider_breakdown().items():
            print(f"{provider:20s} {count:6d}")
    
    if by_transport or show_all:
        print("\nTransport Breakdown:")
        print("-" * 30)
        for transport, count in stats_obj.transport_breakdown().items():
            print(f"{transport:20s} {count:6d}")
    
    if timing or show_all:
        print("\nTiming Statistics:")
        print("-" * 30)
        timing_stats = stats_obj.timing_stats()
        
        if 'overall' in timing_stats and timing_stats['overall']:
            print("Overall:")
            if 'avg_turnaround' in timing_stats['overall']:
                print(f"  Avg Turnaround: {timing_stats['overall']['avg_turnaround']:.2f}s")
        
        if 'tts' in timing_stats and timing_stats['tts']:
            print("\nTTS:")
            for metric, values in timing_stats['tts'].items():
                if isinstance(values, dict) and 'avg' in values:
                    print(f"  {metric}: avg={values['avg']:.2f}s, "
                          f"min={values['min']:.2f}s, max={values['max']:.2f}s")
        
        if 'stt' in timing_stats and timing_stats['stt']:
            print("\nSTT:")
            for metric, values in timing_stats['stt'].items():
                if isinstance(values, dict) and 'avg' in values:
                    print(f"  {metric}: avg={values['avg']:.2f}s, "
                          f"min={values['min']:.2f}s, max={values['max']:.2f}s")
    
    if conversations or show_all:
        print("\nConversation Statistics:")
        print("-" * 30)
        conv_stats = stats_obj.conversation_stats()
        print(f"Total Conversations: {conv_stats['total_conversations']}")
        print(f"Avg Exchanges/Conv: {conv_stats['exchanges_per_conversation']['avg']:.1f}")
        print(f"Avg Duration: {conv_stats['duration_seconds']['avg']:.1f}s")
        print(f"Avg Word Count: {conv_stats['word_count']['avg']:.0f}")
    
    if errors or show_all:
        print("\nError Statistics:")
        print("-" * 30)
        error_stats = stats_obj.error_stats()
        print(f"Total Errors: {error_stats['total_errors']}")
        print(f"Error Rate: {error_stats['error_rate']:.1%}")
        if error_stats['error_types']:
            print("Error Types:")
            for error_type, count in error_stats['error_types'].items():
                print(f"  {error_type}: {count}")
    
    if silence or show_all:
        print("\nSilence Detection Statistics:")
        print("-" * 30)
        vad_stats = stats_obj.silence_detection_stats()
        print(f"VAD Enabled: {vad_stats['vad_enabled_count']}")
        print(f"VAD Disabled: {vad_stats['vad_disabled_count']}")
        print(f"VAD Usage Rate: {vad_stats['vad_usage_rate']:.1%}")
        if 'avg_record_time_with_vad' in vad_stats:
            print(f"Avg Record Time (VAD): {vad_stats['avg_record_time_with_vad']:.1f}s")
        if 'avg_record_time_without_vad' in vad_stats:
            print(f"Avg Record Time (No VAD): {vad_stats['avg_record_time_without_vad']:.1f}s")


@exchanges.command()
@click.option('-c', '--conversation', help='Export specific conversation')
@click.option('-d', '--date', type=click.DateTime(formats=['%Y-%m-%d']),
              help='Export date range')
@click.option('--days', type=int, help='Export last N days')
@click.option('--format', 
              type=click.Choice(['json', 'csv', 'markdown', 'html']),
              default='json',
              help='Export format')
@click.option('--include-audio', is_flag=True, 
              help='Include audio files (creates zip)')
@click.option('--output', '-o', type=click.Path(),
              help='Output file/directory')
def export(conversation, date, days, format, include_audio, output):
    """Export conversations in various formats."""
    reader = ExchangeReader()
    formatter = ExchangeFormatter()
    grouper = ConversationGrouper()
    
    # Determine what to export
    if conversation:
        exchanges = reader.read_conversation(conversation)
    elif date:
        exchanges = list(reader.read_date(date.date()))
    elif days:
        exchanges = list(reader.read_recent(days))
    else:
        # Default to today
        exchanges = list(reader.read_date(datetime.now().date()))
    
    if not exchanges:
        click.echo("No exchanges found to export.", err=True)
        return
    
    # Group into conversations
    conversations = grouper.group_exchanges(exchanges)
    
    # Determine output file
    if not output:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        if format == 'csv':
            output = f"exchanges_{timestamp}.csv"
        elif format == 'markdown':
            output = f"conversations_{timestamp}.md"
        elif format == 'html':
            output = f"conversations_{timestamp}.html"
        else:
            output = f"exchanges_{timestamp}.json"
    
    # Export based on format
    if format == 'json':
        data = []
        for conv in conversations.values():
            data.append(conv.to_dict())
        
        with open(output, 'w') as f:
            json.dump(data, f, indent=2, default=str)
    
    elif format == 'csv':
        with open(output, 'w') as f:
            # Write header
            f.write(formatter.csv_header() + '\n')
            
            # Write exchanges
            for exchange in exchanges:
                f.write(formatter.csv(exchange) + '\n')
    
    elif format == 'markdown':
        with open(output, 'w') as f:
            for conv in conversations.values():
                f.write(formatter.markdown(conv, include_metadata=True))
                f.write('\n\n---\n\n')
    
    elif format == 'html':
        # If multiple conversations, create an index
        if len(conversations) > 1:
            # Create directory for multiple files
            output_dir = Path(output).with_suffix('')
            output_dir.mkdir(exist_ok=True)
            
            # Write individual conversation files
            for conv in conversations.values():
                conv_file = output_dir / f"{conv.id}.html"
                with open(conv_file, 'w') as f:
                    f.write(formatter.html(conv))
            
            click.echo(f"Exported {len(conversations)} conversations to {output_dir}/")
        else:
            # Single conversation
            conv = list(conversations.values())[0]
            with open(output, 'w') as f:
                f.write(formatter.html(conv))
    
    if include_audio:
        click.echo("Audio export not yet implemented", err=True)
    
    click.echo(f"Exported to {output}")


if __name__ == '__main__':
    exchanges()
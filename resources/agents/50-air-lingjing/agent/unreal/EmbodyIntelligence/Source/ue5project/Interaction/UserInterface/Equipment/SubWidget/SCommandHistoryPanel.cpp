#include "SCommandHistoryPanel.h"
#include "Widgets/Layout/SScrollBox.h"
#include "Widgets/Text/STextBlock.h"
#include "Widgets/Layout/SBorder.h"
#include "Widgets/Layout/SSeparator.h"
#include "Misc/DateTime.h"

void SCommandHistoryPanel::Construct(const FArguments& InArgs)
{
	MaxEntries = InArgs._MaxVisibleEntries;

	ChildSlot
	[
		SNew(SBorder)
		.BorderImage(FCoreStyle::Get().GetBrush("ToolPanel.GroupBorder"))
		.Padding(8.0f)
		[
			SNew(SVerticalBox)
			+ SVerticalBox::Slot()
			.AutoHeight()
			[
				SNew(STextBlock)
				.Text(FText::FromString(TEXT("\u5386\u53f2\u6307\u4ee4")))
				.Font(FCoreStyle::GetDefaultFontStyle("Bold", 12))
				.ColorAndOpacity(FLinearColor::White)
			]
			+ SVerticalBox::Slot()
			.AutoHeight()
			.Padding(FMargin(0, 4, 0, 0))
			[
				SNew(SSeparator)
				.Orientation(Orient_Horizontal)
			]
			+ SVerticalBox::Slot()
			.FillHeight(1.0f)
			.Padding(FMargin(0, 4, 0, 0))
			[
				SNew(SScrollBox)
				+ SScrollBox::Slot()
				[
					SNew(STextBlock)
					.Text_Lambda([this]() { return GetHistoryText(); })
					.Font(FCoreStyle::GetDefaultFontStyle("Regular", 9))
					.ColorAndOpacity(FLinearColor(FColor(220, 200, 160)))
					.AutoWrapText(true)
				]
			]
		]
	];
}

void SCommandHistoryPanel::AddCommand(const FString& InType, const FString& InContent)
{
	FCommandEntry Entry;
	Entry.Timestamp = FDateTime::Now().ToString(TEXT("%H:%M:%S"));
	Entry.CommandType = InType;
	Entry.Content = InContent;
	CommandEntries.Add(MoveTemp(Entry));

	if (CommandEntries.Num() > MaxEntries)
	{
		CommandEntries.RemoveAt(0, CommandEntries.Num() - MaxEntries);
	}
}

void SCommandHistoryPanel::ClearCommands()
{
	CommandEntries.Empty();
}

FText SCommandHistoryPanel::GetHistoryText() const
{
	FString Result;
	for (const FCommandEntry& Entry : CommandEntries)
	{
		Result += FString::Printf(TEXT("[%s] %s: %s\n"), *Entry.Timestamp, *Entry.CommandType, *Entry.Content);
	}
	return FText::FromString(Result);
}

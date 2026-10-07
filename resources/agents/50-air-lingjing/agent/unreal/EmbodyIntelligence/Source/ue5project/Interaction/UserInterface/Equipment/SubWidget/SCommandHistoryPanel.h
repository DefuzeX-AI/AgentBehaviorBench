#pragma once

#include "CoreMinimal.h"
#include "Widgets/SCompoundWidget.h"

struct FCommandEntry
{
	FString Timestamp;
	FString CommandType;
	FString Content;
};

class SCommandHistoryPanel : public SCompoundWidget
{
public:
	SLATE_BEGIN_ARGS(SCommandHistoryPanel) {}
	SLATE_ARGUMENT(int32, MaxVisibleEntries)
	SLATE_END_ARGS()

	void Construct(const FArguments& InArgs);

	void AddCommand(const FString& InType, const FString& InContent);
	void ClearCommands();

private:
	TArray<FCommandEntry> CommandEntries;
	int32 MaxEntries = 50;

	FText GetHistoryText() const;
};

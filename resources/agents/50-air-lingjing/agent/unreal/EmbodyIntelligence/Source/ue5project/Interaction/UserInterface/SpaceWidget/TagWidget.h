// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

#include "CoreMinimal.h"
#include "ue5project/Static/Slate/InheritedtStruct.h"
#include "Widgets/SCompoundWidget.h"

/**
 * 
 */
class UE5PROJECT_API STagWidget : public SCompoundWidget
{
public:
	enum class EWidgetType : uint8
	{
		None,
		Equipment,
		TaskPoint
	};
	
	SLATE_BEGIN_ARGS(STagWidget)
	{
		_SColor = FSColor();
		_EquipmentId = FString();
	}
	SLATE_ARGUMENT(FSColor, SColor)
	SLATE_ARGUMENT(FString, EquipmentId)
	SLATE_END_ARGS()

	void Construct(const FArguments& InArgs);
	
	void SetColor(const FSColor& InColor) const;
	void SetTagName(const FString& InEquipmentId);
	void SetWidgetType(const EWidgetType InType);

protected:
	TSharedPtr<STextBlock> TagTextBlock;
	TSharedPtr<SImage> BackgroundImage;
	TSharedPtr<SImage> PointImage;
	
	FString Id;
	EWidgetType WidgetType = EWidgetType::None;

	FReply OnTagButtonClicked() const;
	
};
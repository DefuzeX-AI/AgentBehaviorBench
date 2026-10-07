// Fill out your copyright notice in the Description page of Project Settings.


#include "TagWidget.h"

#include "SpaceWidgetStyleSet.h"
#include "ue5project/Interaction/UserInterface/Equipment/EquipmentWidgetController.h"
#include "ue5project/Scene/Equipment/EquipmentActor.h"
#include "ue5project/Scene/Equipment/FEquipmentController.h"
#include "ue5project/Scene/Task/TaskMatrixController.h"
#include "ue5project/Scene/Task/TaskPointActor.h"
#include "ue5project/Static/Slate/DefaultStyleSet.h"

void STagWidget::Construct(const FArguments& InArgs)
{
	const FSColor Color = InArgs._SColor;
	Id = InArgs._EquipmentId;
	
	const FSlateBrush* WhiteImageBrush = FSpaceWidgetStyleSet::Get()->GetBrush(TEXT("WhiteImageBrush"));
	const FSlateBrush* PointImageBrush = FSpaceWidgetStyleSet::Get()->GetBrush(TEXT("PointImageBrush"));

	const FButtonStyle* NoDrawTypeButtonStyle = FDefaultStyleSet::GetNoDrawTypeButtonStyle();
	const FSlateFontInfo DefaultFontStyle = FCoreStyle::GetDefaultFontStyle("Bold", 11);
	
	ChildSlot
	[
		SNew(SVerticalBox)
		+ SVerticalBox::Slot()
		.AutoHeight()
		[
			SNew(SBox)
			.HeightOverride(18.f)
			.MinDesiredWidth(60.f)
			[
				SNew(SButton)
				.ButtonStyle(NoDrawTypeButtonStyle)
				.ContentPadding(0.f)
				.OnClicked(this, &STagWidget::OnTagButtonClicked)
				[					
					SNew(SOverlay)
					+ SOverlay::Slot()
					[
						SAssignNew(BackgroundImage, SImage)
						.Image(WhiteImageBrush)
						.ColorAndOpacity(Color)
					]
					+ SOverlay::Slot()
					.HAlign(HAlign_Center)
					.VAlign(VAlign_Center)
					[
						SAssignNew(TagTextBlock, STextBlock)
						.Text(FText::FromString(Id))
						.Font(DefaultFontStyle)
						.ColorAndOpacity(FLinearColor::White)
					]
				]
			]
		]
		+ SVerticalBox::Slot()
		.AutoHeight()
		.HAlign(HAlign_Left)
		[
			SAssignNew(PointImage, SImage)
			.Image(PointImageBrush)
			.ColorAndOpacity(Color)
		]
	];
}

void STagWidget::SetColor(const FSColor& InColor) const
{
	if (BackgroundImage.IsValid() && PointImage.IsValid())
	{
		BackgroundImage->SetColorAndOpacity(InColor);
		PointImage->SetColorAndOpacity(InColor);
	}
}

void STagWidget::SetTagName(const FString& InEquipmentId)
{
	Id = InEquipmentId;
	const FString&& TagName = FString::Printf(TEXT(" %s"), *Id);
	if (TagTextBlock.IsValid())
	{
		TagTextBlock->SetText(FText::FromString(TagName));
	}
}

void STagWidget::SetWidgetType(const EWidgetType InType)
{
	WidgetType = InType;
}

FReply STagWidget::OnTagButtonClicked() const
{
	switch (WidgetType)
	{
	case EWidgetType::Equipment:
		if (AEquipmentActor* EquipmentActor = FEquipmentController::Get()->GetEquipment(Id))
		{
			EquipmentActor->UpdateCameraTarget();
			FEquipmentWidgetController::Get()->CreateEquipmentWidget(Id);
		}
		break;
	case EWidgetType::TaskPoint:
		if (ATaskPointActor* TaskPointActor = FTaskMatrixController::Get()->GetTaskPointActor(Id))
		{
			TaskPointActor->UpdateCameraTarget();
		}
		break;
	default: ;
	}
	
	return FReply::Handled();
}



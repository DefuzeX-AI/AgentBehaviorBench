// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

#include "CoreMinimal.h"
#include "ue5project/Static/Slate/InheritedtStruct.h"

class FSpaceWidgetStyleSet final
{
	FSpaceWidgetStyleSet()
	{
		{	// PointImageBrush
			UTexture2D* Texture = LoadObject<UTexture2D>(nullptr, TEXT("/Script/Engine.Texture2D'/EmbodyIntelligence/Program/UserInterface/Textures/SpaceWidget/Point.Point'"));
			if (Texture)
			{
				Texture->AddToRoot();
			}
			FSlateImageBrush* ImageBrush = new FSlateImageBrush(Texture, FVector2D(15.0, 15.0));
			RegisterSlateBrush(TEXT("PointImageBrush"), ImageBrush);
		}
		{	// WhiteImageBrush
			FSlateBrush* Brush = new FSlateBrush;
			Brush->TintColor = FSColor(255, 255, 255, 1.f);
			Brush->DrawAs = ESlateBrushDrawType::RoundedBox;
			Brush->OutlineSettings.RoundingType = ESlateBrushRoundingType::FixedRadius;
			Brush->OutlineSettings.CornerRadii = FVector4(2.0, 2.0, 2.0, 2.0);
			RegisterSlateBrush(TEXT("WhiteImageBrush"), Brush);
		}
	}
	~FSpaceWidgetStyleSet()
	{}

	TMap<FName, FSlateBrush*> BrushNameSlateBrushMap;
	void RegisterSlateBrush(const FName& BrushName, FSlateBrush* InBrush)
	{
		BrushNameSlateBrushMap.Add(BrushName, InBrush);
	}

public:
	static FSpaceWidgetStyleSet* Get()
	{
		static FSpaceWidgetStyleSet Instance;
		return &Instance;
	}

	FSlateBrush* GetBrush(const FName& BrushName) const
	{
		return BrushNameSlateBrushMap.FindRef(BrushName);
	}
};



